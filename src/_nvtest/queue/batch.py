from typing import Generator

from ..test.partition import Partition
from ..test.testcase import TestCase
from .base import Queue


class BatchQueue(Queue):
    def batch_info(self) -> list[list[str]]:
        return [[case.fullname for case in batch] for batch in self.work_items]

    def create_queue(self, work_items: list[Partition]) -> dict[int, Partition]:
        queue: dict[int, Partition] = {}
        n = len(work_items)
        for (i, cases) in enumerate(work_items):
            cases_to_run = [case for case in cases if not case.skip]
            if not cases_to_run:
                continue
            queue[i] = Partition(cases_to_run, i, n)
        return queue

    def refresh(self):
        self.queue = self.create_queue(self.work_items)

    @property
    def cases(self) -> list[TestCase]:
        return [case for batch in self.work_items for case in batch]

    @property
    def cases_done(self) -> int:
        return sum(len(batch) for batch in self._done.values())

    @property
    def cases_running(self) -> int:
        return sum(len(batch) for batch in self._running.values())

    @property
    def cases_notrun(self) -> int:
        return sum(len(batch) for batch in self.queue.values())

    def completed_testcases(self) -> Generator[TestCase, None, None]:
        for batch in self._done.values():
            for case in batch:
                yield case
