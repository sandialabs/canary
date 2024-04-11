from typing import Generator

from ..test.partition import Partition
from ..test.testcase import TestCase
from .base import Queue


class BatchQueue(Queue):
    def batch_info(self) -> list[list[str]]:
        return [[case.fullname for case in batch] for batch in self.work_items]

    def prepare(self) -> None:
        for partition in self.work_items:
            cases_to_run = [case for case in partition if not case.masked]
            if not cases_to_run:
                continue
            self.ready[len(self.ready)] = partition
        self.prepared = True

    def orphaned(self, batch_no: int) -> None:
        assert 0, "Should never get here"

    def done(self, batch_no: int) -> Partition:
        if batch_no not in self.busy:
            raise RuntimeError(f"batch {batch_no} is not running")
        with self.lock():
            self.finished[batch_no] = self.busy.pop(batch_no)
            completed = dict([(_.id, _) for _ in self.completed_testcases()])
            for batch in self.ready.values():
                for case in batch:
                    for i, dep in enumerate(case.dependencies):
                        if dep.id in completed:
                            case.dependencies[i] = completed[dep.id]
        return self.finished[batch_no]

    @property
    def allow_keyboard_interaction(self) -> bool:
        return False

    @property
    def cases(self) -> list[TestCase]:
        return [case for batch in self.work_items for case in batch]

    @property
    def cases_done(self) -> int:
        return sum(len(batch) for batch in self.finished.values())

    @property
    def cases_running(self) -> int:
        return sum(len(batch) for batch in self.busy.values())

    @property
    def cases_notrun(self) -> int:
        return sum(len(batch) for batch in self.ready.values())

    def completed_testcases(self) -> Generator[TestCase, None, None]:
        for batch in self.finished.values():
            for case in batch:
                yield case
