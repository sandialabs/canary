import os
import re
import xml.dom.minidom as xdom
import xml.sax.saxutils
from datetime import datetime
from types import SimpleNamespace

from _nvtest.reporter import Reporter
from _nvtest.test.case import TestCase
from _nvtest.util.filesystem import mkdirp


class JunitReporter(Reporter):
    def create(self, o: str = "./junit.xml") -> None:  # type: ignore
        """Create JUnit report

        Args:
          o: Output file name

        """
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
        file = os.path.abspath(o)
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

    def create_cdata_node(self, text: str) -> xdom.Text:
        node = xdom.CDATASection()
        node.data = cleanup_text(text)
        node.ownerDocument = self
        return node

    def create_testsuite_element(
        self, cases: list[TestCase], tagname: str = "testsuite", **attrs: str
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

    def create_testcase_element(self, case: TestCase) -> xdom.Element:
        """Create a testcase element with the following structure:

        .. code-block: xml

           <testcase name="..." classname="..." time="..." file="...">
             <failure type="..." message="..."> </failure>
             <system-out> ... </system-out>
           </testcase>

        """
        testcase = self.create_element("testcase")
        testcase.setAttribute("name", case.display_name)
        testcase.setAttribute("classname", case.classname)
        testcase.setAttribute("time", str(case.duration))
        testcase.setAttribute("file", getattr(case, "relpath", case.file_path))
        not_done = ("retry", "created", "pending", "ready", "running", "cancelled", "not_run")
        if case.status.value in ("failed", "timeout", "diffed"):
            failure = self.create_element("failure")
            failure.setAttribute("message", f"Test case status: {case.status.value}")
            failure.setAttribute("type", case.status.name)
            testcase.appendChild(failure)
            text = self.create_cdata_node(case.output())
            system_out = self.create_element("system-out")
            system_out.appendChild(text)
            testcase.appendChild(system_out)
            if "CI_SERVER_VERSION_MAJOR" in os.environ:
                # Older versions of gitlab only read from <failure> ... </failure>
                major = int(os.environ["CI_SERVER_VERSION_MAJOR"])
                minor = int(os.environ["CI_SERVER_VERSION_MINOR"])
                if (major, minor) < (16, 5):
                    failure.appendChild(text)
        elif case.status.value in not_done:
            skipped = self.create_element("skipped")
            skipped.setAttribute("message", case.status.value.upper())
            testcase.appendChild(skipped)
        return testcase


def gather_statistics(cases: list[TestCase]) -> SimpleNamespace:
    stats = SimpleNamespace(
        num_skipped=0,
        num_failed=0,
        num_error=0,
        num_tests=0,
        start=datetime.now().timestamp(),
        finish=-1,
    )
    for case in cases:
        if case.status == "masked":
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


def cleanup_text(text: str, escape: bool = False) -> str:
    # First strip ansi color sequences from string
    text = re.sub(r"\033[^m]*m", "", text)
    if escape:
        text = xml.sax.saxutils.escape(text)
    return text
