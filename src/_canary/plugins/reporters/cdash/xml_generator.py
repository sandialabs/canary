# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import importlib.resources as ir
import json
import os
import time
import xml.dom.minidom as xdom
from graphlib import TopologicalSorter
from typing import IO
from typing import TYPE_CHECKING
from typing import Any

from .... import config
from ....test.case import TestCase
from ....test.case import factory as testcase_factory
from ....util import cdash
from ....util import logging
from ....util.filesystem import mkdirp
from ....util.filesystem import working_dir
from ....util.time import strftimestamp
from ....util.time import timestamp
from ....version import version as canary_version
from ..common import TestData

if TYPE_CHECKING:
    from ....session import Session


class CDashXMLReporter:
    def __init__(self, session: "Session | None" = None, dest: str | None = None) -> None:
        self.data = TestData()
        if session:
            for case in session.active_cases():
                self.data.add_test(case)
        if dest is None:
            dest = os.path.join("." if not session else session.work_tree, "CDASH")
        assert dest is not None
        if not os.path.isabs(dest):
            dest = os.path.join(config.invocation_dir, dest)
        self.xml_dir = os.path.abspath(dest)
        self.xml_files: list[str] = []
        self.notes: dict[str, str] = {}

    @classmethod
    def from_json(cls, file: str, dest: str | None = None) -> "CDashXMLReporter":
        """Create an xml report from a json report"""
        dest = dest or os.path.join(os.path.dirname(file), "CDASH")
        self = cls(dest=dest)
        data = json.load(open(file))
        ts: TopologicalSorter = TopologicalSorter()
        for id, state in data.items():
            for name, value in state["properties"].items():
                if name == "dependencies":
                    dependencies = value
                    dep_ids = [d["properties"]["id"] for d in dependencies]
                    ts.add(id, *dep_ids)
                    break
        cases: dict[str, TestCase] = {}
        for id in ts.static_order():
            state = data[id]
            case = testcase_factory(state.pop("type"))
            case.setstate(state)
            for i, dep in enumerate(case.dependencies):
                case.dependencies[i] = cases[dep.id]
            cases[id] = case
        for case in cases.values():
            if not case.masked():
                # case.refresh()
                self.data.add_test(case)
        return self

    def create(
        self,
        buildname: str,
        site: str | None = None,
        track: str | None = None,
        buildstamp: str | None = None,
        generator: str | None = None,
        chunk_size: int | None = None,
    ) -> None:
        """Collect information and create reports"""
        self.meta: dict[str, Any] | None = None
        self.buildname = buildname
        self.site = site or os.uname().nodename
        self.generator = generator or f"canary version {canary_version}"
        if buildstamp is not None and track is not None:
            raise ValueError("mutually exclusive inputs: track, buildstamp")
        if buildstamp is None:
            self.buildstamp = self.generate_buildstamp(track or "Experimental")
        else:
            self.buildstamp = self.validate_buildstamp(buildstamp)
        mkdirp(self.xml_dir)
        try:
            if chunk_size > 0:  # type: ignore
                for cases in chunked(self.data.cases, chunk_size):
                    self.write_test_xml(cases)
            elif chunk_size < 0:  # type: ignore
                self.write_test_xml(self.data.cases)
            else:
                raise ValueError("chunk_size must be a positive integer or -1")
        except ValueError as e:
            raise ValueError(f"invalid chunk_size {chunk_size} \n{e}")
        self.write_notes_xml()

    @staticmethod
    def read_site_info(file, namespace: argparse.Namespace | None = None) -> argparse.Namespace:
        with open(file) as fh:
            doc = xdom.parse(fh)
        if namespace is None:
            namespace = argparse.Namespace()
        fs = doc.getElementsByTagName("Site")[0]
        namespace.site = fs.getAttribute("Name")
        namespace.buildname = fs.getAttribute("BuildName")
        namespace.buildstamp = fs.getAttribute("BuildStamp")
        namespace.generator = fs.getAttribute("Generator")
        return namespace

    def generate_buildstamp(self, track):
        fmt = f"%Y%m%d-%H%M-{track}"
        t = time.localtime(self.data.start)
        return time.strftime(fmt, t)

    def validate_buildstamp(self, buildstamp):
        fmt = "%Y%m%d-%H%M"
        time_part = "-".join(buildstamp.split("-")[:-1])
        try:
            time.strptime(time_part, fmt)
        except ValueError:
            fmt += "-<track>"
            raise ValueError(f"expected build stamp should formatted as {fmt!r}, got {buildstamp}")
        return buildstamp

    @staticmethod
    def post(url: str, project: str, *files: str) -> str | None:
        if not files:
            raise ValueError("No files to post")
        server = cdash.server(url, project)
        ns = CDashXMLReporter.read_site_info(files[0])
        upload_errors = 0
        buildid = None
        for file in files:
            payload = server.upload(
                filename=file,
                sitename=ns.site,
                buildname=ns.buildname,
                buildstamp=ns.buildstamp,
            )
            buildid = buildid or payload["buildid"]
            upload_error = 0 if payload["status"] == "OK" else 1
            upload_errors += upload_error
        if upload_errors:
            logging.warning(f"{upload_errors} files failed to upload to CDash")
        if buildid is None:
            return None
        return f"{url}/buildSummary.php?buildid={buildid}"

    def create_document(self) -> xdom.Document:
        doc = xdom.Document()
        if self.meta is None:
            self.meta = {}
            host = os.uname().nodename
            os_release = config.system.os.release
            os_name = config.system.platform
            os_version = config.system.os.fullversion
            os_platform = config.system.arch
            self.meta["BuildName"] = self.buildname
            self.meta["BuildStamp"] = self.buildstamp
            self.meta["Name"] = self.site
            self.meta["Generator"] = self.generator
            if config.build.compiler.vendor is not None:
                vendor = config.build.compiler.vendor
                version = config.build.compiler.version
                self.meta["CompilerName"] = vendor
                self.meta["CompilerVersion"] = version
            self.meta["Hostname"] = host
            self.meta["OSName"] = os_name
            self.meta["OSRelease"] = os_release
            self.meta["OSVersion"] = os_version
            self.meta["OSPlatform"] = os_platform
        el = doc.createElement("Site")
        for key, value in self.meta.items():
            el.setAttribute(key, str("" if value is None else value))
        doc.appendChild(el)
        return doc

    def write_test_xml(self, cases: list[TestCase]) -> str:
        i = 0
        while True:
            filename = os.path.join(self.xml_dir, f"Test-{i}.xml")
            if not os.path.exists(filename):
                break
            i += 1
        f = os.path.relpath(filename, config.invocation_dir)
        logging.log(logging.INFO, f"WRITING: {len(cases)} test cases to {f}", prefix=None)
        starttime = self.data.start

        doc = self.create_document()
        root = doc.firstChild
        l1 = doc.createElement("Testing")
        add_text_node(l1, "StartDateTime", strftimestamp(starttime))
        add_text_node(l1, "StartTestTime", int(starttime))
        testlist = doc.createElement("TestList")
        for case in cases:
            add_text_node(testlist, "Test", f"./{case.fullname}")
        l1.appendChild(testlist)
        success = ("success", "xfail", "xdiff")

        status: str
        for case in cases:
            exit_value = case.returncode
            fail_reason = None
            if case.status.satisfies(("retry", "created", "pending", "ready", "running", "masked")):
                status = "notdone"
                exit_code = "Not Done"
                completion_status = "notrun"
            elif case.status == "invalid":
                status = "notdone"
                exit_code = "Initialization Error"
                completion_status = "notrun"
            elif case.status == "skipped":
                status = "notdone"
                exit_code = "Skipped"
                completion_status = "notrun"
            elif case.status.value in success:
                status = "passed"
                exit_code = "Passed"
                completion_status = "Completed"
            elif case.status == "diffed":
                status = "failed"
                exit_code = "Diffed"
                completion_status = "Completed"
                fail_reason = case.status.details or "Test diffed"
            elif case.status == "failed":
                status = "failed"
                exit_code = "Failed"
                completion_status = "Completed"
                fail_reason = case.status.details or "Test execution failed"
            elif case.status == "timeout":
                status = "failed"
                exit_code = completion_status = "Timeout"
            elif case.status == "not_run":
                status = "failed"
                exit_code = "Not Run"
                completion_status = "Completed"
                fail_reason = case.status.details or "Test case was unexpectedly not run"
            elif case.status == "cancelled":
                status = "failed"
                exit_code = "Cancelled"
                completion_status = "Completed"
                fail_reason = case.status.details or "Test case was cancelled"
            elif case.status == "unknown":
                status = "failed"
                exit_code = "Unknown"
                completion_status = "Completed"
                fail_reason = case.status.details or "Test case was unexpectedly not run"
            else:
                status = "failed"
                exit_code = "No Status"
                completion_status = "Completed"
            test_node = doc.createElement("Test")
            test_node.setAttribute("Status", status)
            add_text_node(test_node, "Name", case.display_name)
            add_text_node(test_node, "Path", f"./{case.file_path}")
            add_text_node(test_node, "FullName", case.fullname)
            add_text_node(test_node, "FullCommandLine", case.raw_command_line())
            results = doc.createElement("Results")

            add_named_measurement(results, "Exit Code", exit_code)
            add_named_measurement(results, "Exit Value", str(exit_value))
            duration = case.stop - case.start
            add_named_measurement(results, "Execution Time", duration)
            if fail_reason is not None:
                add_named_measurement(results, "Fail Reason", fail_reason)
            add_named_measurement(results, "Completion Status", completion_status)
            add_named_measurement(results, "Command Line", case.raw_command_line(), type="cdata")
            add_named_measurement(results, "Processors", int(case.cpus or 1))
            if case.gpus:
                add_named_measurement(results, "GPUs", case.gpus)
            if url := getattr(case, "url", None):
                add_named_measurement(results, "Test Script", url, type="text/link")
            if case.measurements:
                for name, value in case.measurements.items():
                    if isinstance(value, str) and value.startswith(("https://", "http://")):
                        add_named_measurement(results, name.title(), value, type="text/link")
                    elif isinstance(value, (str, int, float)):
                        add_named_measurement(results, name.title(), value)
                    else:
                        add_named_measurement(results, name.title(), json.dumps(value))
            add_measurement(
                results,
                case.output(compress=True),
                encoding="base64",
                compression="gzip",
            )
            test_node.appendChild(results)

            if case.keywords:
                labels = doc.createElement("Labels")
                for keyword in case.keywords:
                    add_text_node(labels, "Label", keyword)
                test_node.appendChild(labels)

            l1.appendChild(test_node)

        root.appendChild(l1)  # type: ignore
        doc.appendChild(root)  # type: ignore

        with open(filename, "w") as fh:
            self.dump_xml(doc, fh)

        self.validate_xml(filename, schema="Test.xsd")

        return filename

    def write_notes_xml(self) -> str | None:
        if not self.notes:
            return None
        filename = unique_file(self.xml_dir, "Notes", ".xml")
        f = os.path.relpath(filename, config.invocation_dir)
        logging.log(logging.INFO, f"WRITING: Notes.xml to {f}", prefix=None)
        doc = self.create_document()
        root = doc.firstChild
        notes_el = doc.createElement("Notes")
        for name, text in self.notes.items():
            t = timestamp()
            s = strftimestamp(t)
            el = doc.createElement("Note")
            el.setAttribute("Name", str(name))
            add_text_node(el, "Time", t)
            add_text_node(el, "DateTime", s)
            add_text_node(el, "Text", text)
            notes_el.appendChild(el)
        root.appendChild(notes_el)  # type: ignore
        doc.appendChild(root)  # type: ignore
        with open(filename, "w") as fh:
            self.dump_xml(doc, fh)
        self.validate_xml(filename, schema="Notes.xsd")
        return filename

    def dump_xml(self, document: xdom.Document, stream: IO[Any]):
        stream.write(document.toprettyxml(indent="", newl=""))

    def validate_xml(self, file: str, *, schema: str) -> None:
        try:
            import xmlschema  # type: ignore
        except ImportError:
            return
        dir = str(ir.files("_canary").joinpath("plugins/reporters/cdash/validators"))
        with working_dir(dir):
            xml_schema = xmlschema.XMLSchema(schema)
            xml_schema.validate(file)


def add_text_node(parent: xdom.Element, name: str, value: Any, **attrs: Any) -> None:
    child = xdom.Element(name)
    child.ownerDocument = parent.ownerDocument
    for key, val in attrs.items():
        child.setAttribute(key, str(val))
    text = xdom.Text()
    text.data = str(value)
    child.appendChild(text)
    parent.appendChild(child)
    return


def add_cdata_node(parent: xdom.Element, name: str, value: Any, **attrs: Any) -> None:
    child = xdom.Element(name)
    child.ownerDocument = parent.ownerDocument
    for key, val in attrs.items():
        child.setAttribute(key, str(val))
    text = xdom.CDATASection()
    text.data = str(value)
    child.appendChild(text)
    parent.appendChild(child)
    return


def add_measurement(parent: xdom.Element, arg: str, **attrs: str) -> None:
    measurement = xdom.Element("Measurement")
    measurement.ownerDocument = parent.ownerDocument
    add_text_node(measurement, "Value", arg, **attrs)
    parent.appendChild(measurement)


def add_named_measurement(
    parent: xdom.Element,
    name: str,
    arg: str | float | int | None,
    type: str | None = None,
) -> None:
    measurement = xdom.Element("NamedMeasurement")
    measurement.ownerDocument = parent.ownerDocument
    if type == "cdata":
        type = "text/string"
        add_cdata_node(measurement, "Value", arg)
    else:
        if type is None:
            type = "numeric/double" if isinstance(arg, (float, int)) else "text/string"
        add_text_node(measurement, "Value", arg)
    measurement.setAttribute("name", name)
    measurement.setAttribute("type", type)
    parent.appendChild(measurement)


def unique_file(dirname: str, filename: str, ext: str) -> str:
    i = 0
    while True:
        basename = f"{filename}-{i}{ext}" if i else f"{filename}{ext}"
        file = os.path.join(dirname, basename)
        if not os.path.exists(file):
            return file
        i += 1


def chunked(seq, size):
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))
