import sys

from ..session import Session
from ..test.enums import Result
from ..test.testcase import TestCase


class Reporter:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.data = TestData(session)


class TestData:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.start: float = sys.maxsize
        self.finish: float = -1
        self.status: int = 0
        self.cases: list[TestCase] = []
        cases_to_run: list[TestCase] = [c for c in session.cases if not c.skip]
        for case in cases_to_run:
            self.add_test(case)

    def __len__(self):
        return len(self.cases)

    def __iter__(self):
        for case in self.cases:
            yield case

    def update_status(self, case: TestCase) -> None:
        if case.result == Result.DIFF:
            self.status |= 2**1
        elif case.result == Result.FAIL:
            self.status |= 2**2
        elif case.result == Result.TIMEOUT:
            self.status |= 2**3
        elif case.result == Result.NOTDONE:
            self.status |= 2**4
        elif case.result == Result.NOTRUN:
            self.status |= 2**5

    def add_test(self, case: TestCase) -> None:
        if self.start > case.start:
            self.start = case.start
        if self.finish < case.finish:
            self.finish = case.finish
        self.update_status(case)
        self.cases.append(case)
