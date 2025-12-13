# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import heapq
import threading
import time
from collections import Counter
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any

from .protocols import JobProtocol
from .resource_pool.rpool import ResourceUnavailable
from .status import Status
from .util import logging
from .util.time import hhmmss

if TYPE_CHECKING:
    from .resource_pool.rpool import ResourcePool

logger = logging.get_logger(__name__)


class Empty(Exception):
    pass


class Busy(Exception):
    pass


@dataclass(order=True)
class HeapSlot:
    # Negative cost so that heapq is max-heap
    cost: float = field(init=False, repr=False)
    job: JobProtocol = field(compare=False)
    resources: list[dict[str, Any]] = field(compare=False, init=False, repr=False)

    def __post_init__(self):
        self.cost = -self.job.cost()
        self.resources = self.job.required_resources()


class ResourceQueue:
    """Heap-based resource queue for jobs.

    Jobs with largest cost are scheduled first. Respects dependencies
    and exclusive job semantics. Raises Busy if no job can be run
    with available resources.
    """

    def __init__(
        self,
        lock: threading.Lock,
        resource_pool: "ResourcePool",
        jobs: list[JobProtocol] | None = None,
    ) -> None:
        self.lock = lock
        self._heap: list[HeapSlot] = []
        self._busy: dict[str, Any] = {}
        self._finished: dict[str, Any] = {}
        self._dependents: dict[str, list[JobProtocol]] = {}
        self.exclusive_job_id: str | None = None
        self.rpool = resource_pool
        self.prepared = False
        if jobs:
            self.put(*jobs)

    def __len__(self):
        return len(self._heap)

    def prepare(self) -> None:
        """Empty method that a subclass can implement"""
        with self.lock:
            if not self._heap:
                raise Empty()

    def put(self, *jobs: JobProtocol) -> None:
        # Precompute heap
        for job in jobs:
            if job.status.state not in ("READY", "PENDING"):
                raise ValueError(f"Job {job} must be READY or PENDING, got {job.status.state}")
            required = job.required_resources()
            if not required:
                raise ValueError(f"{job}: a test should require at least 1 cpu")
            if not self.rpool.accommodates(required):
                raise ValueError(f"Not enough resources for job {job}")
            slot = HeapSlot(job=job)
            heapq.heappush(self._heap, slot)
            logger.debug(f"Job {job.id} added to queue with cost {-slot.cost}")
            self._dependents[job.id] = list(job.dependencies)

    def get(self) -> JobProtocol:
        with self.lock:
            if not self._heap:
                logger.debug("Queue empty on get()")
                raise Empty

            deferred_slots = []
            while self._heap:
                slot = heapq.heappop(self._heap)
                job = slot.job

                if self.exclusive_job_id and self.exclusive_job_id != job.id:
                    deferred_slots.append(slot)
                    continue

                if job.status.category == "SKIP":
                    logger.debug(f"Job {job.id} with status SKIP and removed from queue")
                    self._finished[job.id] = job
                    continue

                if job.status.state not in ("READY", "PENDING"):
                    # Job will never by ready
                    job.status = Status.ERROR(reason="State became unrunable for unknown reasons")
                    logger.debug(f"Job {job.id} marked ERROR and removed from queue")
                    self._finished[job.id] = job
                    continue

                if job.status.state != "READY":
                    deferred_slots.append(slot)
                    continue

                try:
                    acquired = self.rpool.checkout(slot.resources)
                except ResourceUnavailable:
                    deferred_slots.append(slot)
                    continue

                job.assign_resources(acquired)
                self._busy[job.id] = job
                if job.exclusive:
                    self.exclusive_job_id = job.id

                for slot in deferred_slots:
                    heapq.heappush(self._heap, slot)

                return job

            # Heap exhausted without finding a runnable job
            for slot in deferred_slots:
                heapq.heappush(self._heap, slot)

            if deferred_slots:
                raise Busy
            else:
                raise Empty

    def clear(self, status: str = "CANCELLED") -> None:
        while self._heap:
            slot = self._heap.pop()
            slot.job.set_status(status=status)

    def done(self, job: JobProtocol) -> None:
        with self.lock:
            if job.id not in self._busy:
                raise RuntimeError(f"Job {job} is not running")
            self._finished[job.id] = self._busy.pop(job.id)
            if job.exclusive:
                self.exclusive_job_id = None
                logger.debug(f"Exclusive job {job.id} finished, exclusive lock released")
            self.rpool.checkin(job.free_resources())
            self.update_pending(job)
            logger.debug(f"Job {job.id} marked done")

    def update_pending(self, finished_job: Any) -> None:
        """Update dependencies of jobs still in the heap."""
        dependents = self._dependents.get(finished_job.id)
        if not dependents:
            return
        for job in dependents:
            for i, dep in enumerate(job.dependencies):
                if dep.id == finished_job.id:
                    job.dependencies[i] = finished_job

    def cases(self) -> list[JobProtocol]:
        """Return all jobs in queue, busy, and finished."""
        cases = [slot.job for slot in self._heap]
        cases.extend(self._busy.values())
        cases.extend(self._finished.values())
        return cases

    def status(self, start: float | None = None) -> str:
        def sortkey(x):
            n = 0 if x[0] == "PASS" else 2 if x[0] == "FAIL" else 1
            return (n, x[1])

        with self.lock:
            done = len(self._finished)
            busy = len(self._busy)
            pending = len(self._heap)
            total = done + busy + pending
            totals: Counter[tuple[str, str]] = Counter()
            for job in self._finished.values():
                if job.status.state == "COMPLETE":
                    key = (job.status.category, job.status.status)
                    totals[key] += 1
            row: list[str] = []
            if busy:
                row.append(f"{busy}/{total} [green]RUNNING[/]")
            else:
                row.append(f"{total}/{total} [blue]COMPLETE[/]")
            for key in sorted(totals, key=sortkey):
                color = Status.color_for_category[key[0]]
                row.append(f"{totals[key]} [bold {color}]{key[1]}[/]")
            if start is not None:
                duration = hhmmss(time.time() - start)
                row.append(f"in {duration}")
            return ", ".join(row)
