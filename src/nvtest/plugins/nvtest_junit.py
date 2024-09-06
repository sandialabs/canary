import os
import xml.dom.minidom as xdom
from datetime import datetime

import nvtest
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.test.status import Status
from _nvtest.util import logging

from .reporter import Reporter


@nvtest.plugin.register(scope="report", stage="setup", type="junit")
def setup_parser(parser):
    sp = parser.add_subparsers(dest="child_command", metavar="")
    sp.add_parser("create", help="Create junit report")


@nvtest.plugin.register(scope="report", stage="create", type="junit")
def create_report(args):
    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    reporter = JunitReporter(session)
    if args.child_command == "create":
        reporter.create()
    else:
        raise ValueError(f"{args.child_command}: unknown `nvtest report junit` subcommand")


def strftimestamp(timestamp: float) -> str:
    fmt = "%Y-%m-%dT%H:%M:%S"
    return datetime.fromtimestamp(timestamp).strftime(fmt)


class JunitReporter(Reporter):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.file = os.path.join(session.root, "rspec.xml")

    def create(self) -> None:
        """Collect information and create reports"""
        cases = self.group_testcases_by_status(self.data.cases)

        not_done = Status.members[: Status.members.index("not_run")]
        num_skipped = sum([len(v) for k, v in cases.items() if k in not_done])

        failed = Status.members[Status.members.index("diffed") :]
        num_failed = sum([len(v) for k, v in cases.items() if k in failed])

        doc = xdom.Document()
        suites = doc.createElement("testsuites")
        suite = doc.createElement("testsuite")
        suite.setAttribute("name", "nvtest")
        suite.setAttribute("tests", str(len(self.data.cases)))
        suite.setAttribute("errors", "0")
        suite.setAttribute("skipped", str(num_skipped))
        suite.setAttribute("failures", str(num_failed))
        suite.setAttribute("time", str(self.data.finish - self.data.start))
        suite.setAttribute("timestamp", strftimestamp(self.data.start))
        for case in self.data.cases:
            self.add_test_element(suite, case)
        suites.appendChild(suite)
        doc.appendChild(suites)

        with open(self.file, "w") as fh:
            fh.write(doc.toprettyxml(indent="  ", newl="\n"))

    @staticmethod
    def add_test_element(parent: xdom.Element, case: TestCase) -> None:
        doc = xdom.Document()
        child = doc.createElement("testcase")
        child.setAttribute("name", case.display_name)
        child.setAttribute("classname", case.name.replace(".", "_"))
        child.setAttribute("time", str(case.duration))
        not_done = Status.members[: Status.members.index("not_run")]
        if case.status.value in ("failed", "timeout"):
            el = xdom.Document().createElement("failure")
            el.setAttribute("message", case.status.value.upper())
            child.appendChild(el)
        elif case.status == "diffed":
            el = xdom.Document().createElement("failure")
            el.setAttribute("message", "DIFF")
            child.appendChild(el)
        elif case.status.value in not_done:
            el = xdom.Document().createElement("skipped")
            el.setAttribute("message", case.status.value.upper())
            child.appendChild(el)
        parent.appendChild(child)

    @staticmethod
    def group_testcases_by_status(cases: list[TestCase]) -> dict[str, list[TestCase]]:
        """Group tests by status"""
        grouped: dict[str, list[TestCase]] = {}
        for case in cases:
            grouped.setdefault(case.status.value, []).append(case)
        return grouped
