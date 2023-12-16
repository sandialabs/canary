import glob
import json
import os
import time
import xml.dom.minidom as xdom
from typing import Optional

import nvtest

from .. import config
from ..config.machine import machine_config
from ..session import Session
from ..util import cdash
from ..util import tty
from ..util.filesystem import force_remove
from ..util.filesystem import mkdirp
from ..util.time import strftimestamp
from ..util.time import timestamp
from .common import Reporter as _Reporter


class Reporter(_Reporter):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.xml_dir = os.path.join(config.get("session:work_tree"), "xml")
        self.xml_files: list[str] = []

    def create(
        self,
        project: str,
        buildname: str,
        site: Optional[str] = None,
        track: Optional[str] = None,
        build_stamp: Optional[str] = None,
    ) -> None:
        """Collect information and create reports"""
        self.project = project
        self.buildname = buildname
        self.site = site or os.uname().nodename
        if build_stamp is not None and track is not None:
            raise ValueError("mutually exclusive inputs: track, build_stamp")
        if build_stamp is None:
            self.buildstamp = self.generate_buildstamp(track or "Experimental")
        else:
            self.buildstamp = build_stamp
        force_remove(self.xml_dir)
        mkdirp(self.xml_dir)
        self.write_test_xml()
        self.write_notes_xml()
        self.dump()

    def load(self):
        f = os.path.join(self.xml_dir, ".meta.json")
        with open(f, "r") as fh:
            data = json.load(fh)
        for key, value in data.items():
            setattr(self, key, value)
        self.xml_files = glob.glob(os.path.join(self.xml_dir, "*.xml"))

    def dump(self) -> None:
        f = os.path.join(self.xml_dir, ".meta.json")
        data = {
            "project": self.project,
            "buildname": self.buildname,
            "buildstamp": self.buildstamp,
            "site": self.site,
        }
        with open(f, "w") as fh:
            json.dump(data, fh, indent=2)

    def post(self, url: str) -> None:
        if not self.xml_files:
            self.load()
        upload_errors = 0
        for filename in self.xml_files:
            upload_errors += self.upload_to_cdash(url, filename)
        if upload_errors:
            tty.warn(f"{upload_errors} files failed to upload to CDash")

    @property
    def generator(self):
        return f"nvtest version {nvtest.version}"

    def generate_buildstamp(self, track):
        fmt = f"%Y%m%d-%H%M-{track}"
        t = time.localtime(self.data.start)
        return time.strftime(fmt, t)

    def upload_to_cdash(self, url, filename):
        server = cdash.server(url, self.project)
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
        os_release = machine["os"]["release"]
        os_name = machine["platform"]
        os_version = machine["os"]["fullversion"]
        os_platform = machine["arch"]
        doc = xdom.Document()
        root = doc.createElement("Site")
        add_attr(root, "BuildName", self.buildname)
        add_attr(root, "BuildStamp", self.buildstamp)
        add_attr(root, "Name", self.site)
        add_attr(root, "Generator", self.generator)
        if config.get("build"):
            vendor = config.get("build:compiler:vendor")
            version = config.get("build:compiler:version")
            add_attr(root, "CompilerName", vendor)
            add_attr(root, "CompilerVersion", version)
        add_attr(root, "Hostname", host)
        add_attr(root, "OSName", os_name)
        add_attr(root, "OSRelease", os_release)
        add_attr(root, "OSVersion", os_version)
        add_attr(root, "OSPlatform", os_platform)
        return root

    def write_test_xml(self) -> str:
        filename = os.path.join(self.xml_dir, "Test.xml")
        f = os.path.relpath(filename, config.get("session:invocation_dir"))
        tty.info(f"WRITING: Test.xml to {f}", prefix=None)
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
            if case.masked or case.status == "staged":
                status = "notdone"
                exit_code = "Not Done"
                completion_status = "notrun"
            elif case.status == "timeout":
                status = "failed"
                exit_code = completion_status = "Timeout"
            elif case.status == "diffed":
                status = "failed"
                exit_code = "Diffed"
                completion_status = "Completed"
                fail_reason = "Test diffed"
            elif case.status == "failed":
                status = "failed"
                exit_code = "Failed"
                completion_status = "Completed"
                fail_reason = "Test execution failed"
            elif case.status == "success":
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
            add_measurement(results, name="Processors", value=int(case.cpu_count or 0))
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

    def write_notes_xml(self) -> str:
        filename = os.path.join(self.xml_dir, "Notes.xml")
        f = os.path.relpath(filename, config.get("session:invocation_dir"))
        tty.info(f"WRITING: Notes.xml to {f}", prefix=None)
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
