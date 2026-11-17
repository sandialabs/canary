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
from typing import Literal

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
    # (0.0, 0.0) sentinel means job needs costing
    job: BaseJob = field(compare=False)
    cost: tuple[float, float] = field(default=(0.0, 0.0))
    resources: list["NodeRequest"] = field(compare=False, init=False, repr=False)

    def __post_init__(self):
        self.resources = self.job.required_resources()


class ResourceQueue:
    """Heap-based resource queue for jobs.

    Jobs with largest cost are scheduled first. Respects dependencies
    and exclusive job semantics. Raises Busy if no job can be run
    with available resources.

    Supports dynamic job addition with two cost recalculation modes:
    - "incremental": New jobs are costed with updated scale factors, old jobs retain their costs.
      Jobs run in cohort order (submission time), then by priority within cohort.
    - "total": All jobs are re-costed on each addition, all jobs compete globally by priority.
    """

    def __init__(
        self,
        lock: threading.Lock,
        resource_pool: "ResourcePool",
        store: history.HistoryStore | None = None,
        jobs: list[BaseJob] | None = None,
        cost_recalculation: Literal["incremental", "total"] = "incremental",
    ) -> None:
        self.lock = lock
        self.store = store or history.HistoryStore(None)
        self._heap: list[HeapSlot] = []
        self._busy: dict[str, Any] = {}
        self._finished: dict[str, Any] = {}
        self.exclusive_job_id: str | None = None
        self.rpool = resource_pool
        self.cost_recalculation = cost_recalculation
        self._dirty = False
        self.alogger = logging.AdaptiveDebugLogger(__name__)

        # Incremental mode only: cumulative scale factors
        self._scale_cpu_work_sum = 0.0
        self._scale_max_runtime = 0.0
        self._width: float | None = None

        if jobs:
            self.put(*jobs)

    def __len__(self):
        return len(self._heap)

    def update_costs(self) -> None:
        """Calculate costs for jobs that need costing.

        Incremental mode: cost only new jobs, update scale factors cumulatively.
        Total mode: recost all jobs with fresh scale factors, all get same timestamp.
        """
        with self.lock:
            if not self._dirty:
                return

            if not self._heap:
                self._dirty = False
                return

            now = time.time()

            if self._width is None:
                self._width = float(self.rpool.count("cpus"))

            if self.cost_recalculation == "total":
                all_jobs = [slot.job for slot in self._heap]
                runtimes = {
                    job.id: history.estimate_runtime(job, store=self.store) for job in all_jobs
                }
                cpus = {
                    job.id: sum(_.count("cpus") for _ in job.required_resources())
                    for job in all_jobs
                }

                cpu_work = sum(cpus[j.id] * runtimes[j.id] for j in all_jobs)
                scale = max(cpu_work / self._width, max(runtimes.values()))

                for slot in self._heap:
                    calc_cost = -math.hypot(
                        cpus[slot.job.id] / self._width, runtimes[slot.job.id] / scale
                    )
                    slot.cost = (now, calc_cost)

            else:
                new_jobs = [slot.job for slot in self._heap if slot.cost == (0.0, 0.0)]

                if not new_jobs:
                    self._dirty = False
                    return

                runtimes = {
                    job.id: history.estimate_runtime(job, store=self.store) for job in new_jobs
                }
                cpus = {
                    job.id: sum(_.count("cpus") for _ in job.required_resources())
                    for job in new_jobs
                }

                cpu_work_new = sum(cpus[j.id] * runtimes[j.id] for j in new_jobs)
                self._scale_cpu_work_sum += cpu_work_new
                if runtimes:
                    self._scale_max_runtime = max(
                        self._scale_max_runtime, max(runtimes.values()) if runtimes else 0.0
                    )

                scale = max(self._scale_cpu_work_sum / self._width, self._scale_max_runtime)

                for slot in self._heap:
                    if slot.cost == (0.0, 0.0):
                        calc_cost = -math.hypot(
                            cpus[slot.job.id] / self._width, runtimes[slot.job.id] / scale
                        )
                        slot.cost = (now, calc_cost)

            heapq.heapify(self._heap)
            self._dirty = False

    def put(self, *jobs: BaseJob) -> None:
        with self.lock:
            for job in jobs:
                job.validate_enqueuable()
                required = job.required_resources()
                if not required:
                    raise ValueError(f"{job}: a test should require at least 1 cpu")
                if not self.rpool.accommodates(required):
                    raise ValueError(f"Not enough resources for job {job}")
                slot = HeapSlot(job=job, cost=(0.0, 0.0))
                heapq.heappush(self._heap, slot)
            if jobs:
                self._dirty = True

    def get(self) -> BaseJob:
        if self._dirty:
            self.update_costs()

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
