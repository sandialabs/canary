import os
import sys
import xml.dom.minidom as xdom
import xml.sax.saxutils
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging
from _nvtest.util.filesystem import mkdirp

from .base import Reporter


def setup_parser(parser):
    sp = parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create junit report (must be run in test session directory)")
    p.add_argument("-o", default="junit.xml", help="Output file [default: %(default)s]")


def create_report(args):
    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    reporter = JunitReporter(session)
    if args.child_command == "create":
        reporter.create(file=args.o)
    else:
        raise ValueError(f"nvtest report junit: unknown subcommand {args.child_command!r}")


class JunitReporter(Reporter):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.session = session

    def create(self, file: Optional[str] = None) -> None:
        """Collect information and create reports"""

        doc = JunitDocument()
        root = doc.create_testsuite_element(
            self.data.cases, name=self.get_root_name(), tagname="testsuites"
        )
        groups = self.groupby_classname(self.data.cases)
        for classname, cases in groups.items():
            suite = doc.create_testsuite_element(cases, name=classname)
            for case in cases:
                el = doc.create_testcase_element(case)
                suite.appendChild(el)
            root.appendChild(suite)
        doc.appendChild(root)
        file = os.path.abspath(file or "./junit.xml")
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            fh.write(doc.toprettyxml(indent="  ", newl="\n"))

    @staticmethod
    def get_root_name() -> str:
        name = "NVTest Session"
        if "CI_MERGE_REQUEST_IID" in os.environ:
            name = f"Merge Request {os.environ['CI_MERGE_REQUEST_IID']}"
        elif "CI_JOB_NAME" in os.environ:
            name = os.environ["CI_JOB_NAME"].replace(":", " ")
        return name

    @staticmethod
    def groupby_classname(cases: list[TestCase]) -> dict[str, list[TestCase]]:
        """Group tests by status"""
        grouped: dict[str, list[TestCase]] = {}
        for case in cases:
            grouped.setdefault(case.classname, []).append(case)
        return grouped


class JunitDocument(xdom.Document):
    def create_element(self, tagname: str) -> xdom.Element:
        element = xdom.Element(tagname)
        element.ownerDocument = self
        return element

    def create_text_node(self, text: str) -> xdom.Text:
        node = xdom.Text()
        node.data = xml.sax.saxutils.escape(text)
        node.ownerDocument = self
        return node

    def create_testsuite_element(
        self, cases: list[TestCase], tagname: str = "testsuite", **attrs: str
    ) -> xdom.Element:
        element = self.create_element(tagname)
        stats = gather_statistics(cases)
        for name, value in attrs.items():
            element.setAttribute(name, value)
        element.setAttribute("tests", str(stats.num_tests))
        element.setAttribute("errors", str(stats.num_error))
        element.setAttribute("skipped", str(stats.num_skipped))
        element.setAttribute("failures", str(stats.num_failed))
        element.setAttribute("time", str(stats.time))
        element.setAttribute("timestamp", stats.timestamp)
        return element

    def create_testcase_element(self, case: TestCase) -> xdom.Element:
        element = self.create_element("testcase")
        element.setAttribute("name", case.display_name)
        element.setAttribute("classname", case.classname)
        element.setAttribute("time", str(case.duration))
        element.setAttribute("file", getattr(case, "relpath", case.file_path))
        not_done = ("retry", "created", "pending", "ready", "running", "cancelled", "not_run")
        el: Optional[xdom.Element] = None
        if case.status.value == "failed":
            el = self.create_element("failure")
            el.setAttribute("message", "Test case failed")
            el.setAttribute("type", "Fail")
            text = self.create_text_node(case.output())
            el.appendChild(text)
        elif case.status.value == "timeout":
            el = self.create_element("failure")
            el.setAttribute("message", "Test case timed out")
            el.setAttribute("type", "Timeout")
            text = self.create_text_node(case.output())
            el.appendChild(text)
        elif case.status == "diffed":
            el = self.create_element("failure")
            el.setAttribute("message", "Test case diffed")
            el.setAttribute("type", "Diff")
            text = self.create_text_node(case.output())
            el.appendChild(text)
        elif case.status.value in not_done:
            el = self.create_element("skipped")
            el.setAttribute("message", case.status.value.upper())
        if el is not None:
            element.appendChild(el)
        return element


def gather_statistics(cases: list[TestCase]) -> SimpleNamespace:
    stats = SimpleNamespace(
        num_skipped=0, num_failed=0, num_error=0, num_tests=0, start=sys.maxsize, finish=-1
    )
    for case in cases:
        if case.mask:
            continue
        stats.num_tests += 1
        if case.status.value in ("diffed", "failed", "timeout"):
            stats.num_failed += 1
        elif case.status.value in ("cancelled", "not_run", "skipped"):
            stats.num_skipped += 1
        elif case.status.value in ("retry", "created", "pending", "ready", "running"):
            stats.num_error += 1
        if case.status.complete():
            if case.start > 0 and case.start < stats.start:
                stats.start = case.start
            if case.finish > 0 and case.finish > stats.finish:
                stats.finish = case.finish
    stats.time = max(0.0, stats.finish - stats.start)
    stats.timestamp = datetime.fromtimestamp(stats.start).strftime("%Y-%m-%dT%H:%M:%S")
    return stats
