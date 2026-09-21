# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import heapq
import time
from collections import Counter
from typing import TypeAlias

import canary
from _canary import queue
from _canary.job import BaseJob
from _canary.job import JobPhase
from _canary.util.time import hhmmss

logger = canary.get_logger(__name__)
key_type: TypeAlias = tuple[canary.status.Category, canary.status.Outcome]


class ResourceQueue(queue.ResourceQueue):
    def put(self, *jobs: BaseJob) -> None:
        for job in jobs:
            if not job.is_runnable():
                raise ValueError(f"Job {job} is not runnable ({job.state=})")
        with self.lock:
            for batch in jobs:
                slot = queue.HeapSlot(job=batch)  # ty: ignore[invalid-argument-type]
                heapq.heappush(self._heap, slot)
                logger.debug(f"Job {batch.id} added to queue with cost {-slot.cost}")

    def clear(self, status: str = "CANCELLED", reason: str | None = None, code: int = -1) -> None:
        """Terminate every still-queued (pending) batch and its child jobs.

        The base implementation cancels the object stored in the heap.  For the
        HPC backend that object is a ``TestBatch`` whose ``set_status`` only
        updates the batch's own base status; it does not touch the child
        ``canary.Job`` objects that are ultimately written to the results
        database.  Without propagating the cancellation to the children, a batch
        that was still pending when the run was interrupted would leave its jobs
        with an unset status, surfacing as ``NONE (NONE)`` in ``canary status``.
        """
        if reason is None:
            reason = (
                "Keyboard interrupt"
                if status == "INTERRUPTED"
                else "Cancelled before the batch was submitted"
            )
        child_reason = (
            "Keyboard interrupt"
            if status == "INTERRUPTED"
            else f"Batch cancelled before it was submitted: {reason}"
        )
        while self._heap:
            slot = self._heap.pop()
            batch = slot.job
            try:
                if not batch.state.is_done():
                    batch.set_status(outcome=status, reason=reason, code=code)
                    batch.state.phase = JobPhase.DONE
                for job in batch:  # ty: ignore[not-iterable]
                    if job.state.is_done() and not job.status.is_unset():
                        continue
                    job.set_status(outcome=status, reason=child_reason, code=code)
                    job.state.phase = JobPhase.DONE
                batch.save()
            except Exception:
                logger.exception("Failed to cancel pending batch %s", batch.id[:7])

    def jobs(self) -> list[BaseJob]:
        jobs: list[BaseJob] = [job for slot in self._heap for job in slot.job]  # type: ignore
        jobs.extend([job for batch in self._busy.values() for job in batch])
        jobs.extend([job for batch in self._finished.values() for job in batch])
        return jobs

    def status(self, start: float | None = None) -> str:

        def sortkey(x):
            c, o = x
            if c == canary.status.Category.PASS:
                return 0, o
            elif c == canary.status.Category.FAIL:
                return 2, o
            return 1, o

        with self.lock:
            done = sum([len(_) for _ in self._finished.values()])
            busy = sum([len(_) for _ in self._busy.values()])
            pending = sum([len(_.job) for _ in self._heap])  # type: ignore
            total = done + busy + pending
            totals: Counter[key_type] = Counter()
            job: canary.Job
            for batch in self._finished.values():
                for job in batch:
                    if job.state.is_done():
                        key = (job.status.category, job.status.outcome)
                        totals[key] += 1
            row: list[str] = []
            if busy:
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
