# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys
from typing import TYPE_CHECKING

from ...test.case import TestCase
from ...util import logging

if TYPE_CHECKING:
    from ...session import Session


class TestData:
    def __init__(self) -> None:
        self.start: float = sys.maxsize
        self.stop: float = -1
        self.status: int = 0
        self.cases: list["TestCase"] = []

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
        elif case.status == "not_run":
            self.status |= 2**6

    def add_test(self, case: "TestCase") -> None:
        if case.start > 0 and case.start < self.start:
            self.start = case.start
        if case.stop > 0 and case.stop > self.stop:
            self.stop = case.stop
        self.update_status(case)
        self.cases.append(case)


def load_session() -> "Session":
    from ...session import Session

    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    return session
