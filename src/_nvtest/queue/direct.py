from typing import Generator

from ..test import TestCase
from .base import Queue


class DirectQueue(Queue):
    def __init__(self, cpus: int, workers: int, work_items: list[TestCase]) -> None:
        for case in sorted(work_items, key=lambda c: c.size, reverse=True):
            if case.skip:
                continue
            if case.size > cpus:
                raise ValueError(
                    f"{case!r}: size ({case.size}) exceeds max cpu count ({cpus})"
                )
        for case in work_items:
            for dep in case.dependencies:
                if dep not in work_items:
                    raise ValueError(f"{case}: missing dependency: {dep}")
        super().__init__(cpus, workers, work_items)

    def create_queue(self, work_items: list[TestCase]) -> dict[int, TestCase]:
        queue: dict[int, TestCase] = {}
        for (i, case) in enumerate(work_items):
            if not case.skip:
                queue[i] = case
        return queue

    def refresh(self):
        self.queue = self.create_queue(self.work_items)

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
