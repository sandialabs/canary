from typing import Generator

from ..test import TestCase
from .base import Queue


class DirectQueue(Queue):
    def validate(self) -> None:
        for case in self.work_items:
            if case.masked:
                continue
            if case.cpu_count > self.cpus:
                raise ValueError(
                    f"{case!r}: required cpus ({case.cpu_count}) "
                    f"exceeds max cpu count ({self.cpus})"
                )

    def create_queue(self, work_items: list[TestCase]) -> dict[int, TestCase]:
        queue: dict[int, TestCase] = {}
        for i, case in enumerate(work_items):
            if not case.masked:
                queue[i] = case
        return queue

    def mark_as_orphaned(self, case_no: int) -> None:
        with self.lock():
            self._done[case_no] = self.queue.pop(case_no)
            self._done[case_no].status.set("skipped", "failed dependencies")
            for case in self.queue.values():
                for i, dep in enumerate(case.dependencies):
                    if dep.id == self._done[case_no].id:
                        case.dependencies[i] = self._done[case_no]

    def mark_as_complete(self, case_no: int) -> TestCase:
        if case_no not in self._running:
            raise RuntimeError(f"case {case_no} is not running")
        with self.lock():
            self._done[case_no] = self._running.pop(case_no)
            for case in self.queue.values():
                for i, dep in enumerate(case.dependencies):
                    if dep.id == self._done[case_no].id:
                        case.dependencies[i] = self._done[case_no]
        return self._done[case_no]

    @property
    def cases(self):
        return self.work_items

    @property
    def cases_done(self) -> int:
        return len(self._done.values())

    @property
    def cases_running(self) -> int:
        return len(self._running.values())

    @property
    def cases_notrun(self) -> int:
        return len(self.queue.values())

    def completed_testcases(self) -> Generator[TestCase, None, None]:
        for case in self._done.values():
            yield case
