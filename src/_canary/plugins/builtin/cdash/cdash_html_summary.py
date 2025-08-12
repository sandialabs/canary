# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
import io
import os
import sys
from getpass import getuser

from _canary.util import cdash
from _canary.util import logging
from _canary.util.filesystem import mkdirp
from _canary.util.sendmail import sendmail


def cdash_summary(
    *,
    url: str | None = None,
    project: str | None = None,
    buildgroups: list[str] | None = None,
    mailto: list[str] | None = None,
    file: str | None = None,
    skip_sites: list[str] | None = None,
):
    """Generate a summary of the project's CDash dashboard

    Args:
      buildgroups (list[str]): CDash build groups to pull from CDash. If None, pull all groups.
      mailto (list[str]): Email addresses to send the summary.
      file (str): Filename to write the html summary
      project (str): The CDash project
      skip_sites (list[str]): CDash sites to skip. If None, pull from all sites.

    """
    logging.info("Generating the HTML summary")
    if url is None:
        if "CDASH_URL" not in os.environ:
            raise MissingCIVariable("CDASH_URL")
        url = os.environ["CDASH_URL"]
    if project is None:
        if "CDASH_PROJECT" not in os.environ:
            raise MissingCIVariable("CDASH_PROJECT")
        project = os.environ["CDASH_PROJECT"]

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
    groups: list[str] | None = None,
    skip_sites: list[str] | None = None,
) -> str:
    """Generates a CDash summary page

    Args:
      groups (list[str]): The build groups to include in the summary
      skip_sites (list[str]): Sites to skip

    Returns:
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
    buildgroups: list[str] | None = None,
    skip_sites: list[str] | None = None,
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
            logging.debug(f"Missing 'test' section from {b['buildname']}")
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
    def _link(url: str, php: str, tgt: int | str, *filters: str) -> str:
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
                link = _link(url, "viewTest.php", target, *filters)
                fh.write(tblcell(link, 1, "limegreen"))

            else:
                fh.write("<td colspan=5> Missing </td>")

            fh.write(f"<td>{build['builddate']}, Total time {build['time']} </td>")
            fh.write("</tr>\n")
        fh.write("</table>\n")
    fh.write("</body>\n")
    fh.write("</html>\n")
    return fh.getvalue()


class MissingCIVariable(Exception):
    pass
