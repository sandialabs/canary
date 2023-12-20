import datetime
import glob
import io
import json
import os
import sys
import time
import xml.dom.minidom as xdom
from getpass import getuser
from typing import Optional
from typing import Union

import nvtest

from .. import config
from ..config.machine import machine_config
from ..session import Session
from ..util import cdash
from ..util import tty
from ..util.filesystem import mkdirp
from ..util.sendmail import sendmail
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
        buildstamp: Optional[str] = None,
    ) -> None:
        """Collect information and create reports"""
        self.project = project
        self.meta = None
        if isinstance(site, str) and os.path.isfile(site):
            opts = dict(buildstamp=buildstamp, track=track, buildname=buildname)
            if any(list(opts.values())):
                s = ", ".join(list(opts.keys()))
                raise ValueError(f"site=file incompatible with {s}")
            self.read_site_info(site)
        else:
            self.buildname = buildname
            self.site = site or os.uname().nodename
            if buildstamp is not None and track is not None:
                raise ValueError("mutually exclusive inputs: track, buildstamp")
            if buildstamp is None:
                self.buildstamp = self.generate_buildstamp(track or "Experimental")
            else:
                self.buildstamp = self.validate_buildstamp(buildstamp)
        mkdirp(self.xml_dir)
        self.write_test_xml()
        self.write_notes_xml()
        self.dump()

    def read_site_info(self, file):
        with open(file) as fh:
            doc = xdom.parse(fh)
        fs = doc.getElementsByTagName("Site")[0]
        self.meta = dict(fs.attributes.items())
        self.site = fs.getAttribute("Name")
        self.buildname = fs.getAttribute("BuildName")
        self.buildstamp = fs.getAttribute("BuildStamp")
        return

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

    def generate_buildstamp(self, track):
        fmt = f"%Y%m%d-%H%M-{track}"
        t = time.localtime(self.data.start)
        return time.strftime(fmt, t)

    def validate_buildstamp(self, buildstamp):
        fmt = "%Y%m%d-%H%M"
        time_part = "-".join(buildstamp.split("-")[:-1], fmt)
        try:
            time.strptime(time_part)
        except ValueError:
            fmt += "-<track>"
            raise ValueError(
                f"expected build stamp should formatted as {fmt!r}, got {buildstamp}"
            )
        return buildstamp

    def upload_to_cdash(self, url, filename):
        server = cdash.server(url, self.project)
        rc = server.upload(
            filename=filename,
            sitename=self.site,
            buildname=self.buildname,
            buildstamp=self.buildstamp,
        )
        return rc

    @property
    def site_node(self):
        if self.meta is None:
            self.meta = {}
            host = os.uname().nodename
            machine = machine_config()
            os_release = machine["os"]["release"]
            os_name = machine["platform"]
            os_version = machine["os"]["fullversion"]
            os_platform = machine["arch"]
            self.meta["BuildName"] = self.buildname
            self.meta["BuildStamp"] = self.buildstamp
            self.meta["Name"] = self.site
            self.meta["Generator"] = f"nvtest version {nvtest.version}"
            if config.get("build"):
                vendor = config.get("build:compiler:vendor")
                version = config.get("build:compiler:version")
                self.meta["CompilerName"] = vendor
                self.meta["CompilerVersion"] = version
            self.meta["Hostname"] = host
            self.meta["OSName"] = os_name
            self.meta["OSRelease"] = os_release
            self.meta["OSVersion"] = os_version
            self.meta["OSPlatform"] = os_platform
        el = xdom.Document().createElement("Site")
        for (key, value) in self.meta.items():
            add_attr(el, key, value)
        return el

    def write_test_xml(self) -> str:
        filename = os.path.join(self.xml_dir, "Test.xml")
        f = os.path.relpath(filename, config.get("session:invocation_dir"))
        tty.info(f"WRITING: Test.xml to {f}", prefix=None)
        starttime = self.data.start

        doc = xdom.Document()
        root = self.site_node
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
        root = self.site_node
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


def cdash_summary(
    *,
    url: str,
    project: str,
    buildgroups: Optional[list[str]] = None,
    mailto: Optional[list[str]] = None,
    file: Optional[str] = None,
    skip_sites: Optional[list[str]] = None,
):
    """Generate a summary of the project's CDash dashboard

    Parameters
    ----------
    buildgroups : list of str
        CDash build groups to pull from CDash. If None, pull all groups.
    mailto : list of str
        Email addresses to send the summary.
    file : str
        If not None, filename to write the html summary
    project : str
        The CDash project
    skip_sites : list of str
        CDash sites to skip. If None, pull from all sites.

    """
    tty.info("Generating the HTML summary")
    html_summary = generate_cdash_html_summary(
        url, project, groups=buildgroups, skip_sites=skip_sites
    )
    if mailto is None and file is None:
        sys.stdout.write(html_summary)
        return

    user = getuser()
    today = datetime.date.today()
    if mailto is not None:
        tty.info(f"Sending HTML summary to {','.join(mailto)}")
        st_time = today.strftime("%m/%d/%Y")
        subject = f"{project} CDash Summary for {st_time}"
        sendmail(f"{user}@sandia.gov", mailto, subject, html_summary, subtype="html")

    if file is not None:
        file = os.path.abspath(file)
        tty.info(f"Writing HTML summary to {file}")
        try:
            mkdirp(os.path.dirname(file))
            with open(file, "w") as fh:
                fh.write(html_summary)
        except OSError as e:
            s = "Unknown" if not e.args else e.args[0]
            tty.warn(f"Could not write HTML summary due to OSError ({s})")


def generate_cdash_html_summary(
    url: str,
    project: str,
    *,
    groups: Optional[list[str]] = None,
    skip_sites: Optional[list[str]] = None,
) -> str:
    """Generates a CDash summary page

    Parameters
    ----------
    groups : list of str
        The build groups to include in the summary
    skip_sites : list of str
        Sites to skip

    Returns
    -------
    str
        The rendered HTML summary

    """
    date = datetime.date.today().strftime("%Y-%m-%d")
    build_data = _get_build_data(url, project, date, groups, skip_sites)
    buildgroups = groupby_buildgroup(build_data)
    if groups is not None:
        buildgroups = dict([(_, buildgroups[_]) for _ in groups if _ in buildgroups])
    return _html_summary(url, project, buildgroups)


def groupby_buildgroup(builds: list[dict]) -> dict[str, list[dict]]:
    buildgroups: dict[str, list[dict]] = {}
    for b in builds:
        buildgroups.setdefault(b["buildgroup"], []).append(b)
    return buildgroups


def _get_build_data(
    url: str,
    project: str,
    date: str,
    buildgroups: Optional[list[str]] = None,
    skip_sites: Optional[list[str]] = None,
) -> list[dict]:
    """Categorize failed tests as diffed, failed, and timedout.  CDash does
    not distinguish diffed, failed, and timed out tests.  But, a test can
    add a qualifier, eg, 'Failed (Diffed)'.  Here we take
    advantage of nevada's XML files that add 'Diffed' to the status of
    diffed tests

    """
    server = cdash.server(url, project)
    cdash_builds = server.builds(
        date=date, buildgroups=buildgroups, skip_sites=skip_sites
    )
    for b in cdash_builds:
        tty.info(f"Categorizing tests for build {b['buildname']}")
        if "test" not in b:
            b["test"] = server.empty_test_data()
            continue
        num_failed = b["test"]["fail"]
        if not num_failed:
            continue
        diffed = server.get_failed_tests(b, skip_missing=True, fail_reason="Diffed")
        timeout = server.get_failed_tests(b, skip_missing=True, fail_reason="Timeout")
        num_diffed = len(diffed)
        num_timeout = len(timeout)
        b["test"]["fail_diff"] = num_diffed
        b["test"]["fail_timeout"] = num_timeout
        b["test"]["fail_fail"] = max(num_failed - num_diffed - num_timeout, 0)
    return cdash_builds


def _html_summary(url, project, buildgroups) -> str:
    def _link(url: str, php: str, tgt: Union[int, str], *filters: str) -> str:
        link = '<a href="{0}/{1}?{2}">{3}</a>'.format(url, php, "&".join(filters), tgt)
        return link

    def tblcell(link: str, n: int = 0, color: str = "") -> str:
        if not n:
            return f"<td>{link}</td>"
        else:
            return f'<td bgcolor="{color}">{link}</td>'

    title = f"{project.title()} CDash Summary"
    fh = io.StringIO()

    fh.write("<html>\n")
    fh.write("<head>\n")
    fh.write("<style>\n")
    fh.write("h1 {font-size: 40px;}\n")
    fh.write("h2{ font-size: 30px;}\n")
    fh.write("h3 {font-size: 24px;}\n")
    fh.write("p {font-size: 18px;}\n")
    fh.write(".navbar {background-color: #313236; border-radius: 2px;}\n")
    fh.write(".navbar a {color: #aaa; display: inline-block; font-size: 15px; ")
    fh.write("padding: 10px; text-decoration: none; }\n")
    fh.write(".navbar a:hover { color: #ffffff; }\n")
    fh.write("</style>\n")
    fh.write("</head>\n")

    fh.write("<body>\n")
    fh.write("<style>")
    fh.write("table,th,td {padding:5px; border:1px solid black; ")
    fh.write("border-collapse: collapse; }\n")
    fh.write("tr:nth-child(even) {background-color: #fff;}\n")
    fh.write("tr:nth-child(odd) {background-color: #eee;}\n")
    fh.write("</style>\n")
    fh.write(f"<h2> {title} </h2>\n")

    cols = (
        "Site",
        "Build Name",
        "Revision",
        "Error",
        "Warn",
        "Error",
        "Warn",
        "Not Run",
        "Timeout",
        "Diff",
        "Fail",
        "Pass",
        "Time",
    )
    table_cols = " ".join(f"<th>{_}</th>" for _ in cols)
    for (buildgroup, builds) in buildgroups.items():
        fh.write(f"<h3>{buildgroup}</h3>\n")
        fh.write('<table style="width:100%" boarder="1">\n')
        fh.write("<tr>")
        fh.write("<th colspan=2> &nbsp; </th>")
        fh.write("<th> Update </th>")
        fh.write("<th colspan=2> Configure </th>")
        fh.write("<th colspan=2> Build </th>")
        fh.write("<th colspan=5> Test </th>")
        fh.write("<th> &nbsp; </th>")
        fh.write("</tr>\n")

        fh.write(f"<tr>{table_cols}</tr>\n")

        for build in builds:
            id = build["id"]

            fh.write("<tr>")

            # Site
            filters = [
                f"siteid={build['siteid']}",
                f"project={project}",
                f"currenttime={build['unixtimestamp']}",
            ]
            link = _link(url, "viewSite.php", build["site"], *filters)
            fh.write(tblcell(link))

            target = build["buildname"]
            link = _link(url, "buildSummary.php", target, f"buildid={id}")
            fh.write(tblcell(link))

            # Update
            if build["hasupdate"]:
                target = build["update"]["files"]
                link = _link(url, "viewUpdate.php", target, f"buildid={id}")
                fh.write(tblcell(link))
            else:
                fh.write(tblcell("None"))

            # Configure
            if build["hasconfigure"]:
                data = build["configure"]
                target = data["error"]
                link = _link(url, "viewConfigure.php", target, f"buildid={id}")
                fh.write(tblcell(link, target, "red"))
                target = data["warning"]
                link = _link(url, "viewConfigure.php", target, f"buildid={id}")
                fh.write(tblcell(link, target, "orange"))
            else:
                fh.write("<td colspan=2> Missing </td>")

            # Build
            if build["hascompilation"]:
                data = build["compilation"]

                target = data["error"]
                link = _link(url, "viewBuildError.php", target, f"buildid={id}")
                fh.write(tblcell(link, target, "red"))

                target = data["warning"]
                link = _link(url, "viewBuildError.php", target, f"buildid={id}")
                fh.write(tblcell(link, target, "red"))
            else:
                fh.write("<td colspan=2> Missing </td>")

            # Test
            if build["hastest"]:

                target = build["test"]["notrun"]
                filters = ["onlynotrun", f"buildid={id}"]
                link = _link(url, "viewTest.php", target, *filters)
                fh.write(tblcell(link, target, "orange"))

                target = build["test"].get("fail_timeout", 0)
                filters = [
                    "onlyfailed",
                    f"buildid={id}",
                    "filtercount=2",
                    "showfilters=0",
                    "filtercombine=and",
                    "field1=status",
                    "compare1=61",
                    "value1=Failed",
                    "field2=details",
                    "compare2=63",
                    "value2=Timeout",
                ]
                link = _link(url, "viewTest.php", target, *filters)
                fh.write(tblcell(link, target, "lightcyan"))

                target = build["test"].get("fail_diff", 0)
                filters = [
                    "onlyfailed",
                    f"buildid={id}",
                    "filtercount=2",
                    "showfilters=0",
                    "filtercombine=and",
                    "field1=status",
                    "compare1=61",
                    "value1=Failed",
                    "field2=details",
                    "compare2=63",
                    "value2=Diffed",
                ]
                link = _link(url, "viewTest.php", target, *filters)
                fh.write(tblcell(link, target, "orange"))

                target = build["test"].get("fail_fail", 0)
                filters = [
                    "onlyfailed",
                    f"buildid={id}",
                    "filtercount=3",
                    "showfilters=0",
                    "filtercombine=and",
                    "field1=status",
                    "compare1=61",
                    "value1=Failed",
                    "field2=details",
                    "compare2=64",
                    "value2=Diffed",
                    "field3=details",
                    "compare3=64",
                    "value3=Timeout",
                ]
                link = _link(url, "viewTest.php", target, *filters)
                fh.write(tblcell(link, target, "red"))

                target = build["test"].get("pass", 0)
                filters = ["onlypassed", f"buildid={id}"]
                link = _link(url, "viewTest.php", 0, *filters)
                fh.write(tblcell(link, 1, "limegreen"))

            else:
                fh.write("<td colspan=5> Missing </td>")

            fh.write(f"<td>{build['builddate']}, Total time {build['time']} </td>")
            fh.write("</tr>\n")
        fh.write("</table>\n")
    fh.write("</body>\n")
    fh.write("</html>\n")
    return fh.getvalue()
