# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import importlib.resources as ir
import json
import os
import sys
import time
import xml.dom.minidom as xdom
from typing import IO
from typing import Any

import canary
from _canary.util.compression import targz_compress

from . import interface

logger = canary.get_logger(__name__)


class CDashXMLReporter:
    def __init__(self, dest: str | None = None) -> None:
        self.data = TestData()
        if dest is None:
            dest = os.path.join(".", "CDASH")
        assert dest is not None
        if not os.path.isabs(dest):
            dest = os.path.join(canary.config.invocation_dir, dest)
        self.dest: str = os.path.abspath(dest)
        self.notes: dict[str, str] = {}

    @classmethod
    def from_workspace(cls, dest: str | None = None) -> "CDashXMLReporter":
        workspace = canary.Workspace.load()
        cases = workspace.load_testcases()
        if not cases:
            raise ValueError(f"No results found in {workspace.root}")
        if dest is None:
            dest = str((workspace.view or workspace.sessions_dir) / "CDASH")
        self = cls(dest=dest)
        for case in cases:
            self.data.add_test(case)
        return self

    @classmethod
    def from_json(cls, file: str, dest: str | None = None) -> "CDashXMLReporter":
        """Create an xml report from a json report"""
        raise NotImplementedError("No way of loading the case directly from lock yet")

    #        from _canary.testcase import factory as testcase_factory
    #
    #        dest = dest or os.path.join(os.path.dirname(file), "CDASH")
    #        self = cls(dest=dest)
    #        data = json.load(open(file))
    #        ts: TopologicalSorter = TopologicalSorter()
    #        for id, state in data.items():
    #            for name, value in state["properties"].items():
    #                if name == "dependencies":
    #                    dependencies = value
    #                    dep_ids = [d["properties"]["id"] for d in dependencies]
    #                    ts.add(id, *dep_ids)
    #                    break
    #        cases: dict[str, canary.TestCase] = {}
    #        for id in ts.static_order():
    #            state = data[id]
    #            case = testcase_factory(state.pop("type"))
    #            case.setstate(state)
    #            for i, dep in enumerate(case.dependencies):
    #                case.dependencies[i] = cases[dep.id]
    #            cases[id] = case
    #        for case in cases.values():
    #            # case.refresh()
    #            self.data.add_test(case)
    #        return self

    def create(
        self,
        buildname: str,
        site: str | None = None,
        track: str | None = None,
        buildstamp: str | None = None,
        generator: str | None = None,
        chunk_size: int | None = None,
        subproject_labels: list[str] | None = None,
    ) -> None:
        """Collect information and create reports"""
        self.meta: dict[str, Any] | None = None
        self.buildname = buildname
        self.site = site or os.uname().nodename
        self.generator = generator or f"canary version {canary.version}"
        if buildstamp is not None and track is not None:
            raise ValueError("mutually exclusive inputs: track, buildstamp")
        if buildstamp is None:
            self.buildstamp = self.generate_buildstamp(track or "Experimental")
        else:
            self.buildstamp = self.validate_buildstamp(buildstamp)
        canary.filesystem.mkdirp(self.dest)

        unique_subproject_labels: set[str] = set(subproject_labels or [])
        if label_sets := canary.config.pluginmanager.hook.canary_cdash_labels_for_subproject():
            unique_subproject_labels.update([_ for ls in label_sets for _ in ls if ls])
        for case in self.data.cases:
            if label := canary.config.pluginmanager.hook.canary_cdash_subproject_label(case=case):
                unique_subproject_labels.add(label)
        if unique_subproject_labels:
            subproject_labels = list(unique_subproject_labels)

        if chunk_size is None:
            chunk_size = 500
        if chunk_size > 0:  # type: ignore
            for cases in chunked(self.data.cases, chunk_size):
                self.write_test_xml(cases, subproject_labels=subproject_labels)
        elif chunk_size < 0:  # type: ignore
            self.write_test_xml(self.data.cases, subproject_labels=subproject_labels)
        else:
            raise ValueError("chunk_size must be a positive integer or -1")
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
        subproject_labels: set[str] = set()
        if subprojects := fs.getElementsByTagName("Subproject"):
            for subproject in subprojects:
                if name := subproject.getAttribute("name"):
                    subproject_labels.add(name)
                for label in subproject.getElementsByTagName("Label"):
                    if label.childNodes and (name := label.childNodes[0].nodeValue):  # type: ignore
                        subproject_labels.add(name)
        namespace.subproject_labels = None
        if subproject_labels:
            namespace.subproject_labels = list(subproject_labels)
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
    def post(url: str, project: str, *files: str, done: bool = False) -> str | None:
        if not files:
            raise ValueError("No files to post")
        server = interface.server(url, project)
        ns = CDashXMLReporter.read_site_info(files[0])
        upload_errors = 0
        buildid = None
        for file in files:
            logger.info(f"Posting {file} to {url}")
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
            logger.warning(f"{upload_errors} files failed to upload to CDash")
        if buildid is None:
            return None
        if done:
            try:
                with open(os.path.abspath("./Done.xml"), mode="w") as fh:
                    doc = CDashXMLReporter.create_done_document(buildid, time.time())
                    CDashXMLReporter.dump_xml(doc, fh)
                CDashXMLReporter.validate_xml(fh.name, schema="Done.xsd")
                payload = server.upload(
                    filename=fh.name,
                    sitename=ns.site,
                    buildname=ns.buildname,
                    buildstamp=ns.buildstamp,
                )
            finally:
                os.remove(fh.name)
        return f"{url}/buildSummary.php?buildid={buildid}"

    def create_document(self) -> xdom.Document:
        doc = xdom.Document()
        if self.meta is None:
            self.meta = {}
            host = os.uname().nodename
            os_release = canary.config.get("system:os:release")
            os_name = canary.config.get("system:platform")
            os_version = canary.config.get("system:os:fullversion")
            os_platform = canary.config.get("system:arch")
            self.meta["BuildName"] = self.buildname
            self.meta["BuildStamp"] = self.buildstamp
            self.meta["Name"] = self.site
            self.meta["Generator"] = self.generator
            if vendor := canary.config.get("cmake:compiler:vendor"):
                version = canary.config.get("cmake:compiler:version")
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

    def write_test_xml(
        self, cases: list[canary.TestCase], subproject_labels: list[str] | None = None
    ) -> str:
        i = 0
        while True:
            filename = os.path.join(self.dest, f"Test-{i}.xml")
            if not os.path.exists(filename):
                break
            i += 1
        f = os.path.relpath(filename, canary.config.invocation_dir)
        logger.info(f"Writing {f} ({len(cases)} test cases)")

        doc = self.create_document()
        root = doc.firstChild

        if subproject_labels:
            for label in subproject_labels:
                subproject = doc.createElement("Subproject")
                subproject.setAttribute("name", label)
                add_text_node(subproject, "Label", label)
                root.appendChild(subproject)  # type: ignore

        l1 = doc.createElement("Testing")

        starttime = self.data.start
        add_text_node(l1, "StartDateTime", canary.time.strftimestamp(starttime))
        add_text_node(l1, "StartTestTime", int(starttime))

        testlist = doc.createElement("TestList")
        pm = canary.config.pluginmanager.hook
        for case in cases:
            name = pm.canary_cdash_name(case=case) or case.display_name()
            add_text_node(testlist, "Test", f"./{case.workspace.path.parent}/{name}")
        l1.appendChild(testlist)

        status: str
        pm = canary.config.pluginmanager.hook
        for case in cases:
            exit_value = case.status.code
            fail_reason = None
            if case.status.state != "COMPLETE":
                status = "notdone"
                exit_code = "Not Done"
                completion_status = "notrun"
            elif case.status.category == "SKIP":
                status = "notdone"
                exit_code = "Skipped"
                completion_status = "notrun"
            elif case.status.category == "PASS":
                status = "passed"
                exit_code = "Passed"
                completion_status = "Completed"
            elif case.status.status == "TIMEOUT":
                status = "failed"
                exit_code = completion_status = "Timeout"
            elif case.status.category == "FAIL":
                status = "failed"
                exit_code = case.status.status.title()
                completion_status = "Completed"
                fail_reason = case.status.reason or f"Test {case.status.status.lower()}"
            elif case.status.category == "CANCEL":
                status = "failed"
                exit_code = "Cancelled"
                completion_status = "Completed"
                fail_reason = case.status.reason or "Test case was cancelled"
            else:
                status = "failed"
                exit_code = "No Status"
                completion_status = "Completed"
            test_node = doc.createElement("Test")
            test_node.setAttribute("Status", status)
            name_fmt = canary.config.getoption("name_format")
            name = pm.canary_cdash_name(case=case) or case.display_name()
            fullname = f"{case.workspace.path.parent}/{name}"
            command = case.measurements.data.get("command_line", "")
            add_text_node(test_node, "Name", fullname if name_fmt == "long" else name)
            add_text_node(test_node, "Path", str(case.workspace.dir.parent))
            add_text_node(test_node, "FullName", f"./{fullname}")
            add_text_node(test_node, "FullCommandLine", str(command))
            results = doc.createElement("Results")
            add_named_measurement(results, "Exit Code", exit_code)
            add_named_measurement(results, "Exit Value", str(exit_value))
            duration = max(0.0, case.timekeeper.duration())
            add_named_measurement(results, "Command Line", command, type="cdata")
            add_named_measurement(results, "Execution Time", duration)
            if fail_reason is not None:
                add_named_measurement(results, "Fail Reason", fail_reason)
            add_named_measurement(results, "Completion Status", completion_status)
            add_named_measurement(results, "Processors", int(case.cpus or 1))
            if case.gpus:
                add_named_measurement(results, "GPUs", case.gpus)
            for name, value in pm.canary_cdash_named_measurements(case=case).items():
                add_named_measurement(results, name.title(), value)
            for key, value in case.measurements.items():
                name = key.replace("_", " ").title()
                if key == "command_line":
                    continue
                elif isinstance(value, (str, int, float)):
                    add_named_measurement(results, name, value)
                elif isinstance(value, dict):
                    value = ", ".join(f"{k}={v}" for k, v in value.items())
                    add_named_measurement(results, name, value)
                elif isinstance(value, list):
                    value = ", ".join(str(_) for _ in value)
                    add_named_measurement(results, name, value)
                else:
                    add_named_measurement(results, name, json.dumps(value))
            add_measurement(
                results,
                case.read_output(compress=True),
                encoding="base64",
                compression="gzip",
            )
            test_node.appendChild(results)

            artifacts = []
            for artifact in canary.config.pluginmanager.hook.canary_cdash_artifacts(case=case):
                when = artifact["when"]
                if when == "never":
                    continue
                elif when == "on_success" and case.status.category != "PASS":
                    continue
                elif when == "on_failure" and case.status.category == "PASS":
                    continue
                file = artifact["file"]
                if not os.path.exists(file) and not os.path.isabs(file):
                    if os.path.exists(os.path.join(case.workspace.dir, file)):
                        file = os.path.join(case.workspace.dir, file)
                    elif os.path.exists(os.path.join(case.file.parent, file)):
                        file = os.path.join(case.file.parent, file)
                if os.path.exists(file):
                    artifacts.append(file)
            if artifacts:
                payload = targz_compress(*artifacts, path="artifacts")
                add_named_measurement(
                    test_node,
                    "Attached File",
                    payload,
                    type="file",
                    encoding="base64",
                    compression="tar/gzip",
                    filename="artifacts",
                )

            labels: set[str] = set(
                canary.config.pluginmanager.hook.canary_cdash_labels(case=case) or []
            )
            if label := canary.config.pluginmanager.hook.canary_cdash_subproject_label(case=case):
                labels.add(label)
            if labels:
                el = doc.createElement("Labels")
                for label in labels:
                    add_text_node(el, "Label", label)
                test_node.appendChild(el)

            l1.appendChild(test_node)

        stop = self.data.stop
        add_text_node(l1, "EndDateTime", canary.time.strftimestamp(stop))
        add_text_node(l1, "EndTestTime", int(stop))
        add_text_node(l1, "ElapsedMinutes", int((stop - starttime) / 60.0))

        root.appendChild(l1)  # type: ignore
        doc.appendChild(root)  # type: ignore

        with open(filename, "w") as fh:
            self.dump_xml(doc, fh)

        self.validate_xml(filename, schema="Test.xsd")

        return filename

    def write_notes_xml(self) -> str | None:
        if not self.notes:
            return None
        filename = unique_file(self.dest, "Notes", ".xml")
        f = os.path.relpath(filename, canary.config.invocation_dir)
        logger.info(f"Writing Notes.xml to {f}")
        doc = self.create_document()
        root = doc.firstChild
        notes_el = doc.createElement("Notes")
        for name, text in self.notes.items():
            t = canary.time.timestamp()
            s = canary.time.strftimestamp(t)
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

    @staticmethod
    def dump_xml(document: xdom.Document, stream: IO[Any]):
        stream.write(document.toprettyxml(indent="", newl=""))

    @staticmethod
    def validate_xml(file: str, *, schema: str) -> None:
        try:
            import xmlschema  # type: ignore
        except ImportError:
            return
        dir = str(ir.files("canary_cmake").joinpath("cdash/validators"))
        with canary.filesystem.working_dir(dir):
            xml_schema = xmlschema.XMLSchema(schema)
            xml_schema.validate(file)

    @staticmethod
    def create_done_document(buildid: str, time: float) -> xdom.Document:
        doc = xdom.Document()
        done = doc.createElement("Done")
        done.setAttribute("retries", "1")
        add_text_node(done, "buildId", buildid)
        add_text_node(done, "time", str(time))
        doc.appendChild(done)
        return doc


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
    **attrs: str,
) -> None:
    measurement = xdom.Element("NamedMeasurement")
    measurement.ownerDocument = parent.ownerDocument
    if type == "cdata":
        type = "text/string"
        add_cdata_node(measurement, "Value", arg)
    else:
        if isinstance(arg, (float, int)):
            type = "numeric/double"
        elif isinstance(arg, str) and arg.startswith(("http://", "https://")):
            type = "text/link"
        else:
            type = "text/string"
        add_text_node(measurement, "Value", arg)
    measurement.setAttribute("name", name)
    measurement.setAttribute("type", type)
    for key, val in attrs.items():
        measurement.setAttribute(key, str(val))
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


class TestData:
    def __init__(self) -> None:
        self.start: float = sys.maxsize
        self.stop: float = -1
        self.status: int = 0
        self.cases: list["canary.TestCase"] = []

    def __len__(self):
        return len(self.cases)

    def __iter__(self):
        for case in self.cases:
            yield case

    def update_status(self, case: "canary.TestCase") -> None:
        if case.status.category == "PASS":
            return
        elif case.status.category == "FAIL":
            self.status |= 2**1
        else:
            self.status |= 2**2

    def add_test(self, case: "canary.TestCase") -> None:
        if case.timekeeper.started > 0 and case.timekeeper.finished > 0:
            start = case.timekeeper.started
            finish = case.timekeeper.finished
            if start < self.start:
                self.start = start
            if finish > self.stop:
                self.stop = finish
        self.update_status(case)
        self.cases.append(case)
