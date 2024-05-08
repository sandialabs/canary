import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _nvtest.session import Session
    from _nvtest.test.case import TestCase


class Reporter:
    def __init__(self, session: "Session") -> None:
        self.session = session
        self.data = TestData(session)


class TestData:
    def __init__(self, session: "Session") -> None:
        self.session = session
        self.start: float = sys.maxsize
        self.finish: float = -1
        self.status: int = 0
        self.cases: list["TestCase"] = []
        cases_to_run: list["TestCase"] = [c for c in session.cases if not c.masked]
        for case in cases_to_run:
            self.add_test(case)

    def __len__(self):
        return len(self.cases)

    def __iter__(self):
        for case in self.cases:
            yield case

    def update_status(self, case: "TestCase") -> None:
        if case.status == "diffed":
            self.status |= 2**1
        elif case.status == "failed":
            self.status |= 2**2
        elif case.status == "timeout":
            self.status |= 2**3
        elif case.status == "skipped":  # notdone
            self.status |= 2**4
        elif case.status == "ready":
            self.status |= 2**5
        elif case.status == "skipped":
            self.status |= 2**6

    def add_test(self, case: "TestCase") -> None:
        if self.start > case.start:
            self.start = case.start
        if self.finish < case.finish:
            self.finish = case.finish
        self.update_status(case)
        self.cases.append(case)
