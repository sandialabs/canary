from typing import Generator

from ..test.partition import Partition
from ..test.testcase import TestCase
from .base import Queue


class BatchQueue(Queue):
    def validate(self) -> None: ...

    def batch_info(self) -> list[list[str]]:
        return [[case.fullname for case in batch] for batch in self.work_items]

    def create_queue(self, work_items: list[Partition]) -> dict[int, Partition]:
        queue: dict[int, Partition] = {}
        for partition in work_items:
            cases_to_run = [case for case in partition if not case.masked]
            if not cases_to_run:
                continue
            queue[len(queue)] = partition
        return queue

    def mark_as_orphaned(self, batch_no: int) -> None:
        assert 0, "Should never get here"

    def mark_as_complete(self, batch_no: int) -> Partition:
        if batch_no not in self._running:
            raise RuntimeError(f"batch {batch_no} is not running")
        with self.lock():
            self._done[batch_no] = self._running.pop(batch_no)
            completed = dict([(_.id, _) for _ in self.completed_testcases()])
            for batch in self.queue.values():
                for case in batch:
                    for i, dep in enumerate(case.dependencies):
                        if dep.id in completed:
                            case.dependencies[i] = completed[dep.id]
        return self._done[batch_no]

    @property
    def allow_keyboard_interaction(self) -> bool:
        return False

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
