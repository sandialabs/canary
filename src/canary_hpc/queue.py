# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import heapq
import time
from collections import Counter

import canary
from _canary import queue
from _canary.protocols import JobProtocol
from _canary.status import Status
from _canary.util.time import hhmmss

logger = canary.get_logger(__name__)


class ResourceQueue(queue.ResourceQueue):
    def put(self, *jobs: JobProtocol) -> None:
        for job in jobs:
            if job.status.state not in ("READY", "PENDING"):
                raise ValueError(f"Job {job} must be READY or PENDING, got {job.status.state}")
        with self.lock:
            for batch in jobs:
                slot = queue.HeapSlot(job=batch)  # ty: ignore[invalid-argument-type]
                heapq.heappush(self._heap, slot)
                logger.debug(f"Job {batch.id} added to queue with cost {-slot.cost}")
                self._dependents.update({case.id: case.dependencies for case in batch})

    def update_pending(self, finished_job: JobProtocol) -> None:
        dependents = [dep for case in finished_job for dep in self._dependents.get(case.id, [])]
        if not dependents:
            return
        completed = {case.id: case for case in finished_job}
        for job in dependents:
            for i, dep in enumerate(job.dependencies):
                if dep.id in completed:
                    job.dependencies[i] = completed[dep.id]

    def cases(self) -> list[JobProtocol]:
        cases: list[JobProtocol] = [case for batch in self._heap for case in batch]  # type: ignore
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        return cases

    def status(self, start: float | None = None) -> str:
        def sortkey(x):
            n = 0 if x[0] == "PASS" else 2 if x[0] == "FAIL" else 1
            return (n, x[1])

        with self.lock:
            done = sum([len(_) for _ in self._finished.values()])
            busy = sum([len(_) for _ in self._busy.values()])
            pending = sum([len(_.job) for _ in self._heap])  # type: ignore
            total = done + busy + pending
            totals: Counter[tuple[str, str]] = Counter()
            for batch in self._finished.values():
                for case in batch:
                    if case.status.state == "COMPLETE":
                        key = (case.status.category, case.status.status)
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
