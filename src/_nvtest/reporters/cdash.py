import glob
import os
import sys
import time
import xml.dom.minidom as xdom
from typing import Optional

import nvtest

from ..config.machine import machine_config
from ..session import Session
from ..test.enums import Result
from ..test.testcase import TestCase
from ..util import cdash
from ..util import tty
from ..util.filesystem import mkdirp
from ..util.time import strftimestamp
from ..util.time import timestamp


def report(
    session: Session,
    buildname: Optional[str] = None,
    url: Optional[str] = None,
    project: Optional[str] = None,
    buildgroup: Optional[str] = None,
    site: Optional[str] = None,
):
    cases_to_run = [case for case in session.cases if not case.skip]
    data = TestData(session, cases_to_run)
    reporter = Reporter(
        test_data=data,
        buildname=buildname or "BUILD",
        baseurl=url,
        project=project,
        buildgroup=buildgroup,
        site=site,
    )
    dest = os.path.join(session.work_tree, "cdash")
    reporter.create_cdash_reports(dest=dest)


class TestData:
    def __init__(self, session: Session, cases: Optional[list[TestCase]] = None):
        self.command = "nvtest"
        self.cases: list[TestCase] = []
        self.start: float = sys.maxsize
        self.finish: float = -1
        self.status: int = 0
        if cases is not None:
            for case in cases:
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


class Reporter:
    def __init__(
        self,
        *,
        test_data: TestData,
        buildname: str,
        project: Optional[str] = None,
        baseurl: Optional[str] = None,
        buildgroup: Optional[str] = None,
        site: Optional[str] = os.uname().nodename,
    ):
        if baseurl is not None and project is None:
            raise ValueError("CDash base url requires a project name")
        self.data = test_data
        self.baseurl: Optional[str] = baseurl
        self.project: Optional[str] = project
        self.buildname: str = buildname
        self.buildgroup: str = buildgroup or "Experimental"
        self.site = site or os.uname().nodename

    def create_cdash_reports(self, dest: str = "."):
        """Collect information and create reports"""
        mkdirp(dest)
        self.write_test_xml(dest=dest)
        self.write_notes_xml(dest=dest)
        if self.baseurl is not None:
            self.post_to_cdash(dest)

    def post_to_cdash(self, dest: str):
        xml_files = glob.glob(os.path.join(dest, "*.xml"))
        upload_errors = 0
        for filename in xml_files:
            upload_errors += self.upload_to_cdash(filename)
        if upload_errors:
            tty.warn(f"{upload_errors} files failed to upload to CDash")

    @property
    def generator(self):
        return f"nvtest version {nvtest.version}"

    @property
    def buildurl(self):
        if self.baseurl is None:
            return None
        server = cdash.server(self.baseurl, self.project)
        buildid = server.buildid(
            sitename=self.site,
            buildname=self.buildname,
            buildstamp=self.buildstamp,
        )
        if buildid is None:
            return None
        return f"{self.baseurl}/buildSummary.php?buildid={buildid}"

    @property
    def buildstamp(self):
        fmt = f"%Y%m%d-%H%M-{self.buildgroup}"
        t = time.localtime(self.data.start)
        return time.strftime(fmt, t)

    def upload_to_cdash(self, filename):
        if self.baseurl is None:
            return None
        server = cdash.server(self.baseurl, self.project)
        rc = server.upload(
            filename=filename,
            sitename=self.site,
            buildname=self.buildname,
            buildstamp=self.buildstamp,
        )
        return rc

    def site_node(self):
        host = os.uname().nodename
        machine = machine_config()
        os_release = machine.os.release
        os_name = machine.platform
        os_version = machine.os.fullversion
        os_platform = machine.arch
        doc = xdom.Document()
        root = doc.createElement("Site")
        add_attr(root, "BuildName", self.buildname)
        add_attr(root, "BuildStamp", self.buildstamp)
        add_attr(root, "Name", self.site)
        add_attr(root, "Generator", self.generator)
        compiler_name, compiler_version = "gnu", "9.3"
        add_attr(root, "CompilerName", compiler_name)
        add_attr(root, "CompilerVersion", compiler_version)
        add_attr(root, "Hostname", host)
        add_attr(root, "OSName", os_name)
        add_attr(root, "OSRelease", os_release)
        add_attr(root, "OSVersion", os_version)
        add_attr(root, "OSPlatform", os_platform)
        return root

    def write_test_xml(self, dest: str = ".") -> str:
        filename = os.path.join(dest, "Test.xml")
        tty.info(f"WRITING: Test.xml to {filename}", prefix=None)
        starttime = self.data.start

        doc = xdom.Document()
        root = self.site_node()
        l1 = doc.createElement("Testing")
        add_text_node(l1, "StartDateTime", strftimestamp(starttime))
        add_text_node(l1, "StartTestTime", int(starttime))
        testlist = doc.createElement("TestList")
        for case in self.data:
            add_text_node(testlist, "Test", f"./{case.fullname}")
        l1.appendChild(testlist)

        status: str
        for case in self.data:
            exit_value = case.returncode
            fail_reason = None
            if case.skip or case.result in (Result.NOTDONE, Result.NOTRUN):
                status = "notdone"
                exit_code = "Not Done"
                completion_status = "notrun"
            elif case.result == Result.TIMEOUT:
                status = "failed"
                exit_code = completion_status = "Timeout"
            elif case.result == Result.DIFF:
                status = "failed"
                exit_code = "Diffed"
                completion_status = "Completed"
                fail_reason = "Test diffed"
            elif case.result == Result.FAIL:
                status = "failed"
                exit_code = "Failed"
                completion_status = "Completed"
                fail_reason = "Test execution failed"
            elif case.result == Result.PASS:
                status = "passed"
                exit_code = "Passed"
                completion_status = "Completed"
            else:
                status = "failed"
                exit_code = "No Status"
                completion_status = "Completed"
            test_node = doc.createElement("Test")
            test_node.setAttribute("Status", status)
            add_text_node(test_node, "Name", case.family)
            add_text_node(test_node, "Path", f"./{case.fullname}")
            add_text_node(test_node, "FullName", case.name)
            add_text_node(test_node, "FullCommandLine", case.cmd_line)
            results = doc.createElement("Results")

            add_measurement(results, name="Exit Code", value=exit_code)
            add_measurement(results, name="Exit Value", value=str(exit_value))
            duration = case.finish - case.start
            add_measurement(results, name="Execution Time", value=duration)
            if fail_reason is not None:
                add_measurement(results, name="Fail Reason", value=fail_reason)
            add_measurement(results, name="Completion Status", value=completion_status)
            add_measurement(results, name="Command Line", cdata=case.cmd_line)
            add_measurement(results, name="Processors", value=int(case.size or 0))
            add_measurement(
                results,
                value=case.compressed_log(),
                encoding="base64",
                compression="gzip",
            )
            test_node.appendChild(results)

            labels = doc.createElement("Labels")
            for keyword in case.keywords():
                add_text_node(labels, "Label", keyword)
            test_node.appendChild(labels)

            l1.appendChild(test_node)

        root.appendChild(l1)
        doc.appendChild(root)

        with open(filename, "w") as fh:
            self.dump_xml(doc, fh)
        return filename

    def write_notes_xml(self, dest: str = ".") -> str:
        filename = os.path.join(dest, "Notes.xml")
        tty.info(f"WRITING: Notes.xml to {filename}", prefix=None)
        notes: dict[str, str] = {}
        doc = xdom.Document()
        root = self.site_node()
        notes_el = doc.createElement("Notes")
        for name, text in notes.items():
            t = timestamp()
            s = strftimestamp(t)
            el = doc.createElement("Note")
            el.setAttribute("Name", str(name))
            add_text_node(el, "Time", t)
            add_text_node(el, "DateTime", s)
            add_text_node(el, "Text", text)
            notes_el.appendChild(el)
        root.appendChild(notes_el)
        doc.appendChild(root)
        with open(filename, "w") as fh:
            self.dump_xml(doc, fh)
        return filename

    def dump_xml(self, document, stream):
        stream.write(document.toprettyxml(indent="", newl=""))


def add_text_node(parent_node, child_name, content, **attrs):
    doc = xdom.Document()
    child = doc.createElement(child_name)
    text = str("" if content is None else content)
    text_node = doc.createTextNode(text)
    child.appendChild(text_node)
    for key, value in attrs.items():
        child.setAttribute(key, str("" if value is None else value))
    parent_node.appendChild(child)
    return


def add_attr(node, name, value):
    node.setAttribute(name, str("" if value is None else value))


def alert_node(title, item):
    doc = xdom.Document()
    root = doc.createElement(title)
    add_text_node(root, "BuildLogLine", item["line_no"])
    add_text_node(root, "Text", item["text"])
    add_text_node(root, "SourceFile", item["source_file"])
    add_text_node(root, "SourceLineNumber", item["source_line_no"])
    add_text_node(root, "PreContext", item["pre_context"])
    add_text_node(root, "PostContext", item["post_context"])
    add_text_node(root, "Repeat", 0)
    return root


def add_measurement(parent, name=None, value=None, cdata=None, **attrs):
    type = attrs.pop("type", None)
    if name is not None:
        if isinstance(value, (float, int)):
            type = "numeric/double"
        else:
            type = "text/string"
    key = "Measurement" if name is None else "NamedMeasurement"
    doc = xdom.Document()
    l1 = doc.createElement(key)
    if type is not None:
        l1.setAttribute("type", type)
    if name is not None:
        l1.setAttribute("name", name)
    l2 = doc.createElement("Value")
    for key, val in attrs.items():
        l2.setAttribute(key, str("" if val is None else val))
    if cdata is not None:
        text_node = doc.createCDATASection(cdata)
    else:
        text_node = doc.createTextNode(str("" if value is None else value))
    l2.appendChild(text_node)
    l1.appendChild(l2)
    parent.appendChild(l1)
