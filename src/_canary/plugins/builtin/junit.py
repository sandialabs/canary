# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import re
import xml.dom.minidom as xdom
import xml.sax.saxutils
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Any

from ...util.filesystem import mkdirp
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...testcase import TestCase


@hookimpl(specname="canary_session_reporter")
def junit_reporter() -> CanaryReporter:
    return JunitReporter()


class JunitReporter(CanaryReporter):
    type = "junit"
    description = "JUnit reporter"
    default_output = "junit.xml"

    def create(self, **kwargs: Any) -> None:
        workspace = Workspace.load()
        cases = workspace.load_testcases(latest=True)
        doc = JunitDocument()
        root = doc.create_testsuite_element(cases, name=get_root_name(), tagname="testsuites")
        output = kwargs["output"] or self.default_output
        groups = groupby_classname(cases)
        for classname, cases in groups.items():
            suite = doc.create_testsuite_element(cases, name=classname)
            for case in cases:
                el = doc.create_testcase_element(case)
                suite.appendChild(el)
            root.appendChild(suite)
        doc.appendChild(root)
        file = os.path.abspath(output)
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            fh.write(doc.toprettyxml(indent="  ", newl="\n"))


def get_root_name() -> str:
    name = "Canary Session"
    if "CI_MERGE_REQUEST_IID" in os.environ:
        name = f"Merge Request {os.environ['CI_MERGE_REQUEST_IID']}"
    elif "CI_JOB_NAME" in os.environ:
        name = os.environ["CI_JOB_NAME"].replace(":", " ")
    return name


def groupby_classname(cases: list["TestCase"]) -> dict[str, list["TestCase"]]:
    """Group tests by status"""
    grouped: dict[str, list["TestCase"]] = {}
    for case in cases:
        classname = get_classname(case)
        grouped.setdefault(classname, []).append(case)
    return grouped


def get_classname(case: "TestCase") -> str:
    if "classname" in case.spec.attributes:
        return case.spec.attributes["classname"]
    return case.spec.file_path.parent.name


class JunitDocument(xdom.Document):
    def create_element(self, tagname: str) -> xdom.Element:
        element = xdom.Element(tagname)
        element.ownerDocument = self
        return element

    def create_cdata_node(self, text: str) -> xdom.Text:
        node = xdom.CDATASection()
        node.data = cleanup_text(text)
        node.ownerDocument = self
        return node

    def create_testsuite_element(
        self, cases: list["TestCase"], tagname: str = "testsuite", **attrs: str
    ) -> xdom.Element:
        """Create a testcase element with the following structure

        .. code-block:: xml

           <testsuite tests="..." errors="..." skipped="..." failures="..." time="..." timestamp="...">
           </testsuite>

        """
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

    def create_testcase_element(self, case: "TestCase") -> xdom.Element:
        """Create a testcase element with the following structure:

        .. code-block: xml

           <testcase name="..." classname="..." time="..." file="...">
             <failure type="..." message="..."> </failure>
             <system-out> ... </system-out>
           </testcase>

        """
        testcase = self.create_element("testcase")
        testcase.setAttribute("name", case.display_name)
        testcase.setAttribute("classname", get_classname(case))
        testcase.setAttribute("time", str(case.timekeeper.duration))
        testcase.setAttribute("file", getattr(case, "relpath", case.file_path))
        not_done = (
            "RETRY",
            "CREATED",
            "PENDING",
            "READY",
            "RUNNING",
            "CANCELLED",
            "NOT_RUN",
            "UNKNOWN",
        )
        if case.status.name in ("FAILED", "TIMEOUT", "DIFFED"):
            failure = self.create_element("failure")
            failure.setAttribute("message", f"Test case status: {case.status.name}")
            failure.setAttribute("type", case.status.name)
            testcase.appendChild(failure)
            text = self.create_cdata_node(case.read_output())
            system_out = self.create_element("system-out")
            system_out.appendChild(text)
            testcase.appendChild(system_out)
            if "CI_SERVER_VERSION_MAJOR" in os.environ:
                # Older versions of gitlab only read from <failure> ... </failure>
                major = int(os.environ["CI_SERVER_VERSION_MAJOR"])
                minor = int(os.environ["CI_SERVER_VERSION_MINOR"])
                if (major, minor) < (16, 5):
                    failure.appendChild(text)
        elif case.status.name in not_done:
            skipped = self.create_element("skipped")
            skipped.setAttribute("message", case.status.name)
            testcase.appendChild(skipped)
        return testcase


def gather_statistics(cases: list["TestCase"]) -> SimpleNamespace:
    stats = SimpleNamespace(num_skipped=0, num_failed=0, num_error=0, num_tests=0, time=0.0)
    started_on: datetime | None = None
    finished_on: datetime | None = None
    for case in cases:
        if case.mask:
            continue
        stats.num_tests += 1
        if case.status.name in ("DIFFED", "FAILED", "TIMEOUT"):
            stats.num_failed += 1
        elif case.status.name in ("CANCELLED", "NOT_RUN", "SKIPPED"):
            stats.num_skipped += 1
        elif case.status.name in ("RETRY", "CREATED", "PENDING", "READY", "RUNNING", "INVALID"):
            stats.num_error += 1
        if case.status.name not in ("PENDING", "RUNNING", "READY"):
            t = case.timekeeper.started_on
            if started_on is None:
                if t != "NA":
                    started_on = datetime.fromisoformat(t)
            elif t != "NA" and datetime.fromisoformat(t) < started_on:
                started_on = datetime.fromisoformat(t)
            t = case.timekeeper.finished_on
            if finished_on is None:
                if t != "NA":
                    finished_on = datetime.fromisoformat(t)
            elif t != "NA" and datetime.fromisoformat(t) > finished_on:
                finished_on = datetime.fromisoformat(t)
    stats.started_on = started_on
    stats.finished_on = finished_on
    if started_on is not None and finished_on is not None:
        stats.timestamp = started_on.strftime("%Y-%m-%dT%H:%M:%S")
        stats.time = (finished_on - started_on).total_seconds()
    else:
        stats.timestamp = "NA"
    return stats


def cleanup_text(text: str, escape: bool = False) -> str:
    # First strip ansi color sequences from string
    text = re.sub(r"\033[^m]*m", "", text)
    if escape:
        text = xml.sax.saxutils.escape(text)
    return text
