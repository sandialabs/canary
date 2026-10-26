# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import heapq
import math
import threading
import time
from collections import Counter
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterable

from .. import history
from ..core.job import BaseJob
from ..resource_pool.rpool import ResourceUnavailable
from ..util import logging
from ..util.time import hhmmss

if TYPE_CHECKING:
    from ..resource_pool.rpool import NodeRequest
    from ..resource_pool.rpool import ResourcePool

logger = logging.get_logger(__name__)


class Empty(Exception):
    pass


class Busy(Exception):
    pass


@dataclass(order=True)
class HeapSlot:
    # Negative cost so that heapq is max-heap
    job: BaseJob = field(compare=False)
    cost: float = field(repr=False, default=0.0)
    resources: list["NodeRequest"] = field(compare=False, init=False, repr=False)

    def __post_init__(self):
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
        store: history.HistoryStore | None = None,
        jobs: list[BaseJob] | None = None,
    ) -> None:
        self.lock = lock
        self.store = store or history.HistoryStore(None)
        self._heap: list[HeapSlot] = []
        self._busy: dict[str, Any] = {}
        self._finished: dict[str, Any] = {}
        self.exclusive_job_id: str | None = None
        self.rpool = resource_pool
        self.prepared = False
        self.alogger = logging.AdaptiveDebugLogger(__name__)
        if jobs:
            self.put(*jobs)

    def __len__(self):
        return len(self._heap)

    def prepare(self) -> None:
        """Empty method that a subclass can implement"""
        if self.prepared:
            name = type(self).__name__
            raise RuntimeError(f"{name} already prepared")
        with self.lock:
            if not self._heap:
                raise Empty()
            jobs = [slot.job for slot in self._heap]
            runtimes = {job.id: history.estimate_runtime(job, store=self.store) for job in jobs}
            cpus = {job.id: sum(_.count("cpus") for _ in job.required_resources()) for job in jobs}

            width: float = float(self.rpool.count("cpus"))
            cpu_work: float = sum(cpus[j.id] * runtimes[j.id] for j in jobs)
            scale: float = max(cpu_work / width, max(runtimes.values()))

            for slot in self._heap:
                slot.cost = -math.hypot(cpus[slot.job.id] / width, runtimes[slot.job.id] / scale)

            heapq.heapify(self._heap)
        self.prepared = True

    def put(self, *jobs: BaseJob) -> None:
        if self.prepared:
            name = type(self).__name__
            raise RuntimeError(f"{name}.put() cannot be called after calling {name}.prepare()")
        for job in jobs:
            job.validate_enqueuable()
            required = job.required_resources()
            if not required:
                raise ValueError(f"{job}: a test should require at least 1 cpu")
            if not self.rpool.accommodates(required):
                raise ValueError(f"Not enough resources for job {job}")
            slot = HeapSlot(job=job)
            heapq.heappush(self._heap, slot)

    def get(self) -> BaseJob:
        if not self.prepared:
            name = type(self).__name__
            raise RuntimeError(f"{name}.prepare must be called before calling {name}.get()")

        with self.lock:
            if not self._heap:
                logger.debug("Queue empty on get()")
                raise Empty

            deferred_slots: list[HeapSlot] = []
            while self._heap:
                slot = heapq.heappop(self._heap)
                job = slot.job

                if self.exclusive_job_id and self.exclusive_job_id != job.id:
                    deferred_slots.append(slot)
                    continue

                if job.exclusive and self._busy:
                    deferred_slots.append(slot)
                    continue

                job.refresh_readiness()

                if not job.is_runnable():
                    # Job will never by ready
                    logger.debug(f"Job {job.id[:7]} not runnable and removed from queue")
                    try:
                        job.save()
                    except Exception:
                        logger.exception("Failed to save non-runnable job %s", job.id[:7])
                    self._finished[job.id] = job
                    continue

                if not job.is_ready():
                    deferred_slots.append(slot)
                    continue

                checkout_timeout = job.resource_checkout_timeout()

                try:
                    if checkout_timeout is None:
                        acquired = self.rpool.checkout(slot.resources)
                    else:
                        acquired = self.rpool.checkout(slot.resources, timeout=checkout_timeout)
                except ResourceUnavailable:
                    deferred_slots.append(slot)
                    continue

                job.assign_resources(acquired)
                self._busy[job.id] = job
                if job.exclusive:
                    logger.debug(f"Exclusive job {job.id[:7]} started, exclusive lock obtained")
                    self.exclusive_job_id = job.id

                for slot in deferred_slots:
                    heapq.heappush(self._heap, slot)

                return job

            # Heap exhausted without finding a runnable job
            for slot in deferred_slots:
                heapq.heappush(self._heap, slot)

            if deferred_slots:
                self.alogger.emit(
                    tuple(sorted(self._busy)),
                    f"Queue busy: {len(deferred_slots)} deferred, "
                    f"{len(self._busy)} running (ids={truncate(self._busy)})",
                )
                raise Busy
            else:
                raise Empty

    def clear(self, status: str = "CANCELLED", reason: str | None = None, code: int = -1) -> None:
        """Terminate every still-queued (pending) job.

        A job that never started still needs a terminal status *and* a terminal
        phase so that downstream consumers (the results database, ``canary
        status``, dependency resolution) treat it as finished rather than as an
        in-flight or unset job.  Historically only ``set_status`` was called
        here, which left ``state.phase`` at ``PENDING`` and never persisted the
        job, so an interrupted-while-pending job could surface as ``NONE
        (NONE)``.
        """
        from ..core.job import JobPhase

        if reason is None:
            reason = (
                "Keyboard interrupt"
                if status == "INTERRUPTED"
                else "Cancelled before the job started"
            )
        while self._heap:
            slot = self._heap.pop()
            job = slot.job
            if job.state.is_done():
                continue
            try:
                job.set_status(outcome=status, reason=reason, code=code)
                job.state.phase = JobPhase.DONE
                job.save()
            except Exception:
                logger.exception("Failed to cancel pending job %s", job.id[:7])

    def done(self, job: BaseJob) -> None:
        requested_job = job
        try:
            with self.lock:
                busy_job = self._busy.get(requested_job.id)
                if busy_job is None:
                    logger.error("queue.done() called for non-busy job %s", requested_job.id[:7])
                    return

                resources = busy_job.free_resources()
                self.rpool.checkin(resources)

                self._busy.pop(requested_job.id, None)
                self._finished[busy_job.id] = busy_job
                if busy_job.exclusive:
                    self.exclusive_job_id = None
                    logger.debug(
                        "Exclusive job %s finished, exclusive lock released", busy_job.id[:7]
                    )
                logger.debug("Job %s marked done", busy_job.id[:7])
        except Exception:
            logger.exception("Failed to mark %s as done", requested_job.id[:7])

    def jobs(self) -> list[BaseJob]:
        """Return all jobs in queue, busy, and finished."""
        jobs = [slot.job for slot in self._heap]
        jobs.extend(self._busy.values())
        jobs.extend(self._finished.values())
        return jobs

    def pending(self) -> list[BaseJob]:
        return [slot.job for slot in self._heap]

    def status(self, start: float | None = None) -> str:
        from ..core.status import Category
        from ..core.status import Outcome

        def sortkey(x):
            n = 0 if x[0] == Category.PASS else 2 if x[0] == Category.FAIL else 1
            return (n, x[1])

        with self.lock:
            done = len(self._finished)
            busy = len(self._busy)
            pending = len(self._heap)
            total = done + busy + pending
            totals: Counter[tuple[Category, Outcome]] = Counter()
            for job in self._finished.values():
                if job.state.is_done():
                    key = (job.status.category, job.status.outcome)
                    totals[key] += 1
            row: list[str] = []
            if pending:
                row.append(f"{busy}/{total} [green]RUNNING[/]")
            else:
                row.append(f"{total}/{total} [blue]COMPLETE[/]")
            for key in sorted(totals, key=sortkey):
                color = key[0].rich_color()
                row.append(f"{totals[key]} [{color}]{key[1].name}[/]")
            if start is not None:
                duration = hhmmss(time.time() - start)
                row.append(f"in {duration}")
            return ", ".join(row)


def truncate(items: Iterable[str]) -> str:
    ids = [item[:7] for item in items]
    if len(ids) > 5:
        ids = [ids[0], ids[1], ids[2], "…", ids[-2], ids[-1]]
    return ",".join(ids)
