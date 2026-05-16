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

    def cases(self) -> list[BaseJob]:
        cases: list[BaseJob] = [case for slot in self._heap for case in slot.job]  # type: ignore
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        return cases

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
            case: canary.Job
            for batch in self._finished.values():
                for case in batch:
                    if case.state.is_done():
                        key = (case.status.category, case.status.outcome)
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
