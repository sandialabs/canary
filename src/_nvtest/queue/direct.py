from typing import TYPE_CHECKING
from typing import Generator

from .base import Queue

if TYPE_CHECKING:
    from ..test.testcase import TestCase


class DirectQueue(Queue):

    def validate(self) -> None:
        for case in self.work_items:
            if case.masked:
                continue
            if case.processors > self.cpus:
                raise ValueError(
                    f"{case!r}: required cpus ({case.processors}) "
                    f"exceeds max cpu count ({self.cpus})"
                )

    def prepare(self) -> None:
        self.validate()
        for i, case in enumerate(self.work_items):
            if not case.masked:
                self.ready[len(self.ready)] = case
        self.prepared = True

    def orphaned(self, case_no: int) -> None:
        with self.lock():
            self.finished[case_no] = self.ready.pop(case_no)
            self.finished[case_no].status.set("skipped", "failed dependencies")
            for case in self.ready.values():
                for i, dep in enumerate(case.dependencies):
                    if dep.id == self.finished[case_no].id:
                        case.dependencies[i] = self.finished[case_no]

    def done(self, case_no: int) -> "TestCase":
        if case_no not in self.busy:
            raise RuntimeError(f"case {case_no} is not running")
        with self.lock():
            self.finished[case_no] = self.busy.pop(case_no)
            for case in self.ready.values():
                for i, dep in enumerate(case.dependencies):
                    if dep.id == self.finished[case_no].id:
                        case.dependencies[i] = self.finished[case_no]
        return self.finished[case_no]

    @property
    def cases(self):
        return self.work_items

    @property
    def cases_done(self) -> int:
        return len(self.finished.values())

    @property
    def cases_running(self) -> int:
        return len(self.busy.values())

    @property
    def cases_notrun(self) -> int:
        return len(self.ready.values())

    def completed_testcases(self) -> Generator["TestCase", None, None]:
        for case in self.finished.values():
            yield case
