import glob
import json
import os
import time
import xml.dom.minidom as xdom
from io import StringIO

import nvtest

from .. import config
from ..util import cdash
from ..util import tty
from ..util.filesystem import mkdirp
from ..util.time import strftimestamp
from ..util.time import timestamp


class Reporter:
    def __init__(
        self,
        *,
        cdash_buildname,
        files,
        cdash_project=None,
        cdash_baseurl=None,
        cdash_buildgroup="Experimental",
        cdash_site=os.uname().nodename,
        dest="./cdash",
    ):
        if cdash_baseurl is not None and cdash_project is None:
            raise ValueError("CDash base url requires a project name")
        if cdash_project is not None and cdash_baseurl is None:
            raise ValueError("CDash project name requires a base url")
        self.test = test_data(*files)
        self.dest = os.path.abspath(dest)
        self.cdash_baseurl = cdash_baseurl
        self.cdash_project = cdash_project
        self.cdash_buildname = cdash_buildname
        self.cdash_buildgroup = cdash_buildgroup
        self.cdash_site = cdash_site
        self.returncode = None

    def __enter__(self):
        self.returncode = None
        self.test.load()
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        self.returncode = 0 if ex_type is None else 1
        return

    def create_cdash_reports(self):
        """Collect information and create reports"""
        mkdirp(self.dest)
        failed_stages = 0
        self.write_test_xml()
        if self.test.status != 0:
            tty.error(f"test:status = {self.test.status}")
            failed_stages += 1
        self.write_notes_xml()
        if self.cdash_baseurl is not None:
            self.post_to_cdash()
        if failed_stages:
            raise RuntimeError("One or more BnB stages failed")

    def post_to_cdash(self):
        xml_files = glob.glob(os.path.join(self.dest, "*.xml"))
        upload_errors = 0
        for filename in xml_files:
            upload_errors += self.upload_to_cdash(filename)
        if upload_errors:
            tty.warn(f"{upload_errors} files failed to upload to CDash")

    @property
    def cdash_generator(self):
        return f"nvtest version {nvtest.version}"

    @property
    def cdash_buildurl(self):
        if self.cdash_baseurl is None:
            return None
        server = cdash.server(self.cdash_baseurl, self.cdash_project)
        buildid = server.buildid(
            sitename=self.cdash_site,
            buildname=self.cdash_buildname,
            buildstamp=self.cdash_buildstamp,
        )
        if buildid is None:
            return None
        return f"{self.cdash_baseurl}/buildSummary.php?buildid={buildid}"

    @property
    def cdash_buildstamp(self):
        fmt = f"%Y%m%d-%H%M-{self.cdash_buildgroup}"
        return "BUILDSTAMP"  # TODO
        return time.strftime(fmt, 0)

    def upload_to_cdash(self, filename):
        if self.cdash_baseurl is None:
            return None
        server = cdash.server(self.cdash_baseurl, self.cdash_project)
        rc = server.upload(
            filename=filename,
            sitename=self.cdash_site,
            buildname=self.cdash_buildname,
            buildstamp=self.cdash_buildstamp,
        )
        return rc

    def site_node(self):
        host = os.uname().nodename
        os_release = config.get("machine:os:release")
        os_name = config.get("machine:platform")
        os_version = config.get("machine:os:fullversion")
        os_platform = config.get("machine:arch")
        doc = xdom.Document()
        root = doc.createElement("Site")
        add_attr(root, "BuildName", self.cdash_buildname)
        add_attr(root, "BuildStamp", self.cdash_buildstamp)
        add_attr(root, "Name", self.cdash_site)
        add_attr(root, "Generator", self.cdash_generator)
        compiler_name, compiler_version = "gnu", "9.3"
        add_attr(root, "CompilerName", compiler_name)
        add_attr(root, "CompilerVersion", compiler_version)
        add_attr(root, "Hostname", host)
        add_attr(root, "OSName", os_name)
        add_attr(root, "OSRelease", os_release)
        add_attr(root, "OSVersion", os_version)
        add_attr(root, "OSPlatform", os_platform)
        return root

    def write_test_xml(self):
        tty.info("Writing Test.xml")
        starttime = self.test.results["starttime"]
        command = self.test.results["command"]
        status = self.test.results["returncode"]
        tests = self.test.results["tests"]["cases"]

        doc = xdom.Document()
        root = self.site_node()
        l1 = doc.createElement("Testing")
        add_text_node(l1, "StartDateTime", strftimestamp(starttime))
        add_text_node(l1, "StartTestTime", int(starttime))
        testlist = doc.createElement("TestList")
        for test in tests:
            add_text_node(testlist, "Test", f"./{test['name']}")
        l1.appendChild(testlist)

        for test in tests:
            result = test["result"]
            exit_value = test["returncode"]
            fail_reason = None
            if test.get("skip") or result in ("notdone", "notrun"):
                status = "notdone"
                exit_code = "Not Done"
                completion_status = "notrun"
            elif result == "timeout":
                status = "failed"
                exit_code = completion_status = "Timeout"
            elif result == "diff":
                status = "failed"
                exit_code = "Diffed"
                completion_status = "Completed"
                fail_reason = "Test diffed"
            elif result == "fail":
                status = "failed"
                exit_code = "Failed"
                completion_status = "Completed"
                fail_reason = "Test execution failed"
            elif result == "pass":
                status = "passed"
                exit_code = "Passed"
                completion_status = "Completed"
            else:
                status = "failed"
                exit_code = "No Status"
                completion_status = "Completed"
            test_node = doc.createElement("Test")
            test_node.setAttribute("Status", status)
            add_text_node(test_node, "Name", test["case"])
            add_text_node(test_node, "Path", f"./{test['path']}")
            add_text_node(test_node, "FullName", test["name"])
            commands = test["command"].split("\n")
            command = "".join(commands[-1:])
            add_text_node(test_node, "FullCommandLine", command)
            results = doc.createElement("Results")

            add_measurement(results, name="Exit Code", value=exit_code)
            add_measurement(results, name="Exit Value", value=str(exit_value))
            duration = test["endtime"] - test["starttime"]
            add_measurement(results, name="Execution Time", value=duration)
            if fail_reason is not None:
                add_measurement(results, name="Fail Reason", value=fail_reason)
            add_measurement(results, name="Completion Status", value=completion_status)
            add_measurement(results, name="Command Line", cdata=test["command"])
            add_measurement(
                results,
                name="Processors",
                value=int(test["resources"]["processors"] or 0),
            )
            log = test["log"] or "Log not found"
            add_measurement(results, value=log, encoding="base64", compression="gzip")
            test_node.appendChild(results)

            labels = doc.createElement("Labels")
            for keyword in test["keywords"]:
                add_text_node(labels, "Label", keyword)
            test_node.appendChild(labels)

            l1.appendChild(test_node)

        root.appendChild(l1)
        doc.appendChild(root)

        f = os.path.join(self.dest, "Test.xml")
        with open(f, "w") as fh:
            self.dump_xml(doc, fh)
        return f

    def write_notes_xml(self):
        tty.info("Writing Notes.xml")
        s = StringIO()
        notes = {}
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
        f = os.path.join(self.dest, "Notes.xml")
        with open(f, "w") as fh:
            self.dump_xml(doc, fh)
        return f

    def dump_xml(self, document, stream):
        stream.write(document.toprettyxml(indent="", newl=""))


class test_data:
    def __init__(self, *files):
        self.files = files

    def load(self):
        to_merge = []
        missing = 0
        for file in self.files:
            if not os.path.exists(file):
                missing += 1
                tty.error(f"{file}: file does not exist")
                continue
            to_merge.append(json.load(open(file)))
        self.results = self.merge(*to_merge)
        self.status = 1 if missing else self.results["returncode"]

    def merge(self, *dicts_to_merge):
        merged = dicts_to_merge[0]
        command = [merged["nvtest"]["command"]]
        cases = merged["nvtest"]["tests"]["cases"]
        ti = merged["nvtest"]["starttime"]
        tf = merged["nvtest"]["endtime"]
        for fd in dicts_to_merge[1:]:
            if not fd:
                continue
            assert "nvtest" in fd
            for stat in ("pass", "notdone", "notrun", "diff", "fail", "timeout"):
                n = merged["nvtest"]["tests"].get(stat, 0)
                n += fd["nvtest"]["tests"].get(stat, 0)
                merged["nvtest"]["tests"][stat] = n
            if fd["nvtest"]["starttime"] < merged["nvtest"]["starttime"]:
                merged["nvtest"]["starttime"] = fd["nvtest"]["starttime"]
                merged["nvtest"]["startdate"] = fd["nvtest"]["startdate"]
            if fd["nvtest"]["endtime"] > merged["nvtest"]["endtime"]:
                merged["nvtest"]["endtime"] = fd["nvtest"]["endtime"]
                merged["nvtest"]["enddate"] = fd["nvtest"]["enddate"]
            ti = min(ti, fd["nvtest"]["starttime"])
            tf = max(tf, fd["nvtest"]["endtime"])
            cases.extend(fd["nvtest"]["tests"]["cases"])
            command.append(fd["nvtest"]["command"])
        merged["nvtest"]["starttime"] = ti
        merged["nvtest"]["endtime"] = tf
        merged["nvtest"]["command"] = " & ".join(command)
        merged["nvtest"]["returncode"] = self.compute_returncode(merged)
        return merged["nvtest"]

    @staticmethod
    def compute_returncode(results):
        """"""
        returncode = 0
        for stat in ("pass", "notdone", "notrun", "diff", "fail", "timeout"):
            n = results["nvtest"]["tests"].get(stat, 0)
            for i in range(n):
                if stat == "diff":
                    returncode |= 2**1
                elif stat == "fail":
                    returncode |= 2**2
                elif stat == "timeout":
                    returncode |= 2**3
                elif stat == "notdone":
                    returncode |= 2**4
                elif stat == "notrun":
                    returncode |= 2**5
        return returncode


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
