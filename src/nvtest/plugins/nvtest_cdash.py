import argparse
import datetime
import glob
import io
import os
import sys
import time
import xml.dom.minidom as xdom
from getpass import getuser
from typing import Optional
from typing import Union

import nvtest
from _nvtest import config
from _nvtest.config.machine import machine_config
from _nvtest.session import Session
from _nvtest.util import cdash
from _nvtest.util import gitlab
from _nvtest.util import logging
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.sendmail import sendmail
from _nvtest.util.time import strftimestamp
from _nvtest.util.time import timestamp

from .reporter import Reporter


@nvtest.plugin.register(scope="report", stage="setup", type="cdash")
def setup_parser(parser):
    sp = parser.add_subparsers(dest="child_command", metavar="")
    p = sp.add_parser("create", help="Create CDash XML files")
    p.add_argument(
        "--build",
        dest="buildname",
        metavar="name",
        help="The name of the build that will be reported to CDash.",
    )
    p.add_argument(
        "--site",
        metavar="name",
        help="The site name that will be reported to CDash. " "[default: current system hostname]",
    )
    p.add_argument(
        "-f",
        metavar="file",
        help="Read site, build, and buildstamp from this XML "
        "file (eg, Build.xml or Configure.xml)",
    )
    p.add_argument(
        "-d",
        metavar="directory",
        help="Write reports to this directory [default: $session/_reports/cdash]",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--track",
        metavar="track",
        help="Results will be reported to this group on CDash [default: Experimental]",
    )
    group.add_argument(
        "--build-stamp",
        dest="buildstamp",
        metavar="stamp",
        help="Instead of letting the CDash reporter prepare the buildstamp which, "
        "when combined with build name, site and project, uniquely identifies the "
        "build, provide this argument to identify the build yourself. "
        "Format: %%Y%%m%%d-%%H%%M-<track>",
    )

    p = sp.add_parser("post", help="Post CDash XML files")
    p.add_argument(
        "--project",
        required=True,
        metavar="project",
        help="The CDash project",
    )
    p.add_argument(
        "--url",
        metavar="url",
        required=True,
        help="The base CDash url (do not include project)",
    )
    p.add_argument("files", nargs="*", help="XML files to post")


@nvtest.plugin.register(scope="report", stage="create", type="cdash")
def create_reports(args):
    if args.child_command == "post" and args.files:
        url = CDashReporter.post(args.url, args.project, *args.files)
        logging.info(f"Files uploaded to {url}")
        return
    else:
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")
        reporter = CDashReporter(session, dest=args.d)
        if args.child_command == "create":
            if args.f:
                opts = dict(
                    buildstamp=args.buildstamp,
                    track=args.track,
                    buildname=args.buildname,
                )
                if any(list(opts.values())):
                    s = ", ".join(list(opts.keys()))
                    raise ValueError(f"-f {args.f!r} incompatible with {s}")
                reporter.read_site_info(args.f, namespace=args)
            reporter.create(
                args.buildname,
                site=args.site,
                track=args.track,
                buildstamp=args.buildstamp,
            )
        elif args.child_command == "post":
            if not args.files:
                args.files = glob.glob(os.path.join(reporter.xml_dir, "*.xml"))
            if not args.files:
                raise ValueError("nvtest report cdash post: no xml files to post")
            url = reporter.post(args.url, args.project, *args.files)
            logging.info(f"Files uploaded to {url}")
        else:
            raise ValueError(f"{args.child_command}: unknown `nvtest report cdash` subcommand")
        return 0


class CDashReporter(Reporter):
    def __init__(self, session: Session, dest: Optional[str] = None) -> None:
        super().__init__(session)
        dest = dest or os.path.join(session.root, "_reports/cdash")
        self.xml_dir = os.path.abspath(dest)
        self.xml_files: list[str] = []

    def create(
        self,
        buildname: str,
        site: Optional[str] = None,
        track: Optional[str] = None,
        buildstamp: Optional[str] = None,
    ) -> None:
        """Collect information and create reports"""
        self.meta = None
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

    @staticmethod
    def read_site_info(file, namespace: Optional[argparse.Namespace] = None) -> argparse.Namespace:
        with open(file) as fh:
            doc = xdom.parse(fh)
        if namespace is None:
            namespace = argparse.Namespace()
        fs = doc.getElementsByTagName("Site")[0]
        namespace.site = fs.getAttribute("Name")
        namespace.buildname = fs.getAttribute("BuildName")
        namespace.buildstamp = fs.getAttribute("BuildStamp")
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
    def post(url: str, project: str, *files: str) -> Optional[str]:
        if not files:
            raise ValueError("No files to post")
        server = cdash.server(url, project)
        ns = CDashReporter.read_site_info(files[0])
        upload_errors = 0
        for file in files:
            upload_errors += server.upload(
                filename=file,
                sitename=ns.site,
                buildname=ns.buildname,
                buildstamp=ns.buildstamp,
            )
        if upload_errors:
            logging.warning(f"{upload_errors} files failed to upload to CDash")
        buildid = server.buildid(
            sitename=ns.site, buildname=ns.buildname, buildstamp=ns.buildstamp
        )
        if buildid is None:
            return None
        return f"{url}/buildSummary.php?buildid={buildid}"

    @property
    def site_node(self):
        import nvtest

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
        for key, value in self.meta.items():
            add_attr(el, key, value)
        return el

    def write_test_xml(self) -> str:
        filename = os.path.join(self.xml_dir, "Test.xml")
        f = os.path.relpath(filename, config.get("session:invocation_dir"))
        logging.log(logging.INFO, f"WRITING: Test.xml to {f}", prefix=None)
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
            if case.mask or case.status.value in ("created", "pending", "ready", "cancelled"):
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
            add_measurement(results, name="Processors", value=int(case.processors or 0))
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
        filename = unique_file(self.xml_dir, "Notes", ".xml")
        f = os.path.relpath(filename, config.get("session:invocation_dir"))
        logging.log(logging.INFO, f"WRITING: Notes.xml to {f}", prefix=None)
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
    logging.info("Generating the HTML summary")
    html_summary = generate_cdash_html_summary(
        url, project, groups=buildgroups, skip_sites=skip_sites
    )
    if mailto is None and file is None:
        sys.stdout.write(html_summary)
        return

    user = getuser()
    today = datetime.date.today()
    if mailto is not None:
        logging.info(f"Sending HTML summary to {','.join(mailto)}")
        st_time = today.strftime("%m/%d/%Y")
        subject = f"{project} CDash Summary for {st_time}"
        sendmail(f"{user}@sandia.gov", mailto, subject, html_summary, subtype="html")

    if file is not None:
        file = os.path.abspath(file)
        logging.info(f"Writing HTML summary to {file}")
        try:
            mkdirp(os.path.dirname(file))
            with open(file, "w") as fh:
                fh.write(html_summary)
        except OSError as e:
            s = "Unknown" if not e.args else e.args[0]
            logging.warning(f"Could not write HTML summary due to OSError ({s})")


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
    cdash_builds = server.builds(date=date, buildgroups=buildgroups, skip_sites=skip_sites)
    for b in cdash_builds:
        logging.info(f"Categorizing tests for build {b['buildname']}")
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
    for buildgroup, builds in buildgroups.items():
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


def create_issues_from_failed_tests(
    *,
    access_token: str,
    cdash_url: str,
    cdash_project: str,
    gitlab_url: str,
    gitlab_project_id: Union[int, str],
    date: Optional[str] = None,
    filtergroups: Optional[list[str]] = None,
    skip_sites: Optional[list[str]] = None,
    dont_close_missing: bool = False,
) -> None:
    """Create issues on GitLab from failing tests on CDash

    Args:
        cdash_url: The base CDash url, do not include project
        cdash_project: The CDash project
        gitlab_url: The GitLab project url
        gitlab_project_id: The GitLab project's integer ID
        access_token: The GitLab access token.  Must have API read/write priveleges
        date: Date to retrieve from CDash
        filtergroups: Groups to pull down from CDash.  Defaults to "Nightly"
        skip_sites: Sites (systems) on which to ignore issues. Accepts Python
          regular expressions
        dont_close_missing: Don't close GitLab issues that are missing from CDash

    """
    filtergroups = filtergroups or ["Nightly"]
    server = cdash.server(cdash_url, cdash_project)
    builds = server.builds(date=date, buildgroups=filtergroups, skip_sites=skip_sites)
    tests: list[dict] = []
    for build in builds:
        tests.extend(server.get_failed_tests(build, skip_missing=True))
    test_groups = groupby_status_and_testname(tests)
    issue_data = []
    for _, group in test_groups.items():
        for test_name, test_realizations in group.items():
            issue = generate_test_issue(test_name, test_realizations)
            issue_data.append(issue)
    repo = gitlab.repo(
        url=gitlab_url, access_token=access_token, project_id=int(gitlab_project_id)
    )
    for issue in issue_data:
        create_or_update_test_issues(repo, issue)
    if not dont_close_missing:
        close_test_issues_missing_from_cdash(repo, issue_data)


def groupby_status_and_testname(tests):
    """Group CDash tests by status and then name

    Notes
    -----
    Groups tests as:

    .. code-block: yaml

        {
            status: {
                test_name: [
                    test_realization_1,
                    test_realization_2,
                    ...,
                    test_realization_n
                ],
            }
        }

    """
    details_map = {
        "Timeout (Timeout)": "Timeout",
        "Completed (Diffed)": "Diffed",
        "Completed (Failed)": "Failed",
    }
    grouped = {}
    logging.info("Grouping failed tests by status and name")
    for test in tests:
        name = test["name"].split(".")[0]
        details = test.pop("details")
        status = details_map.get(details, "Unknown")
        test["fail_reason"] = status
        grouped.setdefault(status, {}).setdefault(name, []).append(test)
    logging.info("Done grouping failed tests by status and name")
    for gn, gt in grouped.items():
        logging.info(f"{len(gt)} tests {gn}")
    return grouped


def generate_test_issue(name, realizations):
    fail_reason = realizations[0]["fail_reason"]
    script_link = realizations[0]["script"]
    script_name = os.path.basename(script_link)
    description = io.StringIO()
    description.write(f"## {fail_reason} test\n\n")
    description.write(f"- Test name: `{name}`\n")
    description.write(f"- Test script: [{script_name}]({script_link})\n")
    description.write(
        "\n-------------\n"
        "Issue automatically generated from a corresponding failed test on CDash.\n"
    )
    s_today = datetime.date.today().strftime("%b %d, %Y")
    notes = io.StringIO()
    m = {"Diffed": "diffing", "Failed": "failing", "Timeout": "timing out"}
    notes.write(f"Realizations {m[fail_reason]} as of {s_today}:\n\n")
    sites = []
    for realization in realizations:
        site = realization["site"]
        link = realization["details_link"]
        rname = realization["name"]
        target = f"{rname} site={site}"
        build_type = realization["build_type"]
        cc = f"{realization['compilername']}@{realization['compilerversion']}"
        target += f" build_type={build_type} %{cc}"
        notes.write(f"- [`{target}`]({link})\n")
        sites.append(site)
    legacy_title = f"TEST {fail_reason.upper()}: {name}"
    title = f"{name}: {fail_reason}"
    issue_data = dict(
        status=fail_reason,
        name=name,
        description=description.getvalue(),
        notes=notes.getvalue(),
        legacy_title=legacy_title,
        title=title,
        sites=sites,
        fail_reason=fail_reason,
    )
    return issue_data


def create_or_update_test_issues(repo, issue_data):
    existing_issues = repo.issues()
    existing_test_issues = [_ for _ in existing_issues if is_test_issue(_)]
    existing = find_existing_issue(issue_data, existing_test_issues)
    if existing is not None:
        update_existing_issue(repo, existing, issue_data)
    else:
        create_new_issue(repo, issue_data)


def close_test_issues_missing_from_cdash(repo, current_issue_data):
    existing_issues = repo.issues()
    existing_test_issues = [_ for _ in existing_issues if is_test_issue(_)]
    for existing_issue in existing_test_issues:
        if existing_issue["state"] != "opened":
            continue
        for current_issue in current_issue_data:
            if existing_issue["title"] == current_issue["title"]:
                break
            elif existing_issue["title"] == current_issue["legacy_title"]:
                break
        else:
            # Issue is open, but not in the CDash failed tests. Must have been fixed and
            # not closed.
            logging.info(f"Closing issue {existing_issue['title']}")
            params = {"state_event": "close", "add_labels": "test::fixed"}
            repo.edit_issue(existing_issue["iid"], data=params)


def is_test_issue(issue, include_blacklisted=False):
    if not include_blacklisted:
        if "test::blacklisted" in issue["labels"]:
            return False
    return any([label.startswith("test::") for label in issue["labels"]])


def find_existing_issue(new_issue, existing_issues):
    label = test_status_label(new_issue["fail_reason"])
    for issue in existing_issues:
        if label in issue["labels"] and issue["title"] == new_issue["title"]:
            return issue
        elif label in issue["labels"] and issue["title"] == new_issue["legacy_title"]:
            return issue


def update_existing_issue(repo, existing, updated_issue_data):
    fail_reason = updated_issue_data["fail_reason"]
    title = updated_issue_data["title"]
    description = updated_issue_data["description"]
    labels = [test_status_label(fail_reason)]
    labels.append("Stage::To Do")
    labels.extend([site_label(_) for _ in updated_issue_data["sites"]])
    params = {"title": title, "description": description}
    add = [_ for _ in labels if _ not in existing["labels"]]
    if add:
        params["add_labels"] = ",".join(add)
    remove = []
    for label in existing["labels"]:
        if label.startswith("system: ") and label not in labels:
            remove.append(label)
        elif label.startswith("Stage::") and label != "Stage::To Do":
            remove.append(label)
    if remove:
        params["remove_labels"] = ",".join(remove)
    if existing["state"] == "closed":
        params["state_event"] = "reopen"
    s = "Reopening" if params.get("state_event") else "Updating"
    logging.info(f"{s} issue {title}")
    iid = existing["iid"]
    repo.edit_issue(iid, data=params)
    repo.edit_issue(iid, notes=updated_issue_data["notes"])


def create_new_issue(repo, new_issue_data):
    title = new_issue_data["title"]
    fail_reason = new_issue_data["fail_reason"]
    description = new_issue_data["description"]
    labels = [test_status_label(fail_reason)]
    labels.append("Stage::To Do")
    labels.extend([site_label(_) for _ in new_issue_data["sites"]])
    params = {"title": title, "description": description, "labels": ",".join(labels)}
    logging.info(f"Creating new issue for {title}, with labels {params['labels']}")
    iid = repo.new_issue(data=params)
    if iid:
        repo.edit_issue(iid, notes=new_issue_data["notes"])


def test_status_label(status):
    if status == "Diffed":
        label = "diff"
    elif status == "Failed":
        label = "fail"
    elif status == "Timeout":
        label = "timeout"
    else:
        label = status
    assert label in ("diff", "fail", "timeout")
    scoped_label = f"test::{label}"
    return scoped_label


def site_label(site):
    return f"system: {site}"


def unique_file(dirname: str, filename: str, ext: str) -> str:
    i = 0
    while True:
        basename = f"{filename}-{i}{ext}" if i else f"{filename}{ext}"
        file = os.path.join(dirname, basename)
        if not os.path.exists(file):
            return file
        i += 1
