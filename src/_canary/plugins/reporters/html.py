# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import string
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from ... import config
from ...test.case import TestCase
from ...util import logging
from ...util.filesystem import force_remove
from ...util.filesystem import mkdirp
from ..hookspec import hookimpl
from ..types import CanaryReport

if TYPE_CHECKING:
    from ...session import Session


@hookimpl
def canary_session_report() -> CanaryReport:
    return HTMLReport()


class HTMLReport(CanaryReport):
    type = "html"
    description = "HTML reporter"
    multipage = True

    def create(self, session: "Session | None" = None, **kwargs: Any) -> None:
        if session is None:
            raise ValueError("canary report html: session required")

        dest = string.Template(kwargs["dest"]).safe_substitute(canary_work_tree=session.work_tree)
        self.html_dir = os.path.join(dest, "HTML")
        self.cases_dir = os.path.join(self.html_dir, "cases")
        self.index = os.path.join(dest, "canary-report.html")

        force_remove(self.html_dir)
        mkdirp(self.cases_dir)
        for case in session.active_cases():
            file = os.path.join(self.cases_dir, f"{case.id}.html")
            with open(file, "w") as fh:
                self.generate_case_file(case, fh)
        with open(self.index, "w") as fh:
            self.generate_index(session, fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logging.info(f"HTML report written to {f}")

    @property
    def style(self) -> str:
        ts = "<style>\n"
        ts += "table{font-family:arial,sans-serif;border-collapse:collapse;}\n"
        ts += "td, th {border: 1px solid #dddddd; text-align: left; "
        ts += "padding: 8px; width: 100%}\n"
        ts += "tr:nth-child(even) {background-color: #dddddd;}\n"
        ts += "</style>"
        return ts

    @property
    def head(self) -> str:
        return f"<head>\n{self.style}\n</head>\n"

    def generate_case_file(self, case: TestCase, fh: TextIO) -> None:
        if case.masked():
            return
        fh.write("<html>\n")
        fh.write("<body>\n<table>\n")
        fh.write(f"<tr><td><b>Test:</b> {case.display_name}</td></tr>\n")
        if case.defective():
            fh.write("<tr><td><b>Status:</b> Defective</td></tr>\n")
        else:
            fh.write(f"<tr><td><b>Status:</b> {case.status.name}</td></tr>\n")
        fh.write(f"<tr><td><b>Exit code:</b> {case.returncode}</td></tr>\n")
        fh.write(f"<tr><td><b>ID:</b> {case.id}</td></tr>\n")
        fh.write(f"<tr><td><b>Duration:</b> {case.duration}</td></tr>\n")
        fh.write("</table>\n")
        fh.write("<h2>Test output</h2>\n<pre>\n")
        if case.defective():
            fh.write(f"{case.defect}\n")
        elif os.path.exists(case.logfile()):
            with open(case.logfile()) as fp:
                fh.write(fp.read())
        else:
            fh.write("Log file does not exist\n")
        fh.write("</pre>\n</body>\n</html>\n")

    def generate_index(self, session: "Session", fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Canary Summary</h1>\n")
        fh.write("<table>\n<tr>")
        for col in (
            "Site",
            "Project",
            "Not Run",
            "Timeout",
            "Fail",
            "Diff",
            "Pass",
            "Defective",
            "Cancelled",
            "Total",
        ):
            fh.write(f"<th>{col}</th>")
        fh.write("</tr>\n")
        totals: dict[str, list[TestCase]] = {}
        for case in session.active_cases():
            group = "Defective" if case.defective() else case.status.name.title()
            totals.setdefault(group, []).append(case)
        fh.write("<tr>")
        fh.write(f"<td>{config.system.host}</td>")
        fh.write(f"<td>{config.build.project}</td>")
        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Defective", "Cancelled"):
            if group not in totals:
                fh.write("<td>0</td>")
            else:
                n = len(totals[group])
                file = os.path.join(self.html_dir, "%s.html" % "".join(group.split()))
                fh.write(f'<td><a href="file://{file}">{n}</a></td>')
                with open(file, "w") as fp:
                    self.generate_group_index(totals[group], fp)
        file = os.path.join(self.html_dir, "Total.html")
        fh.write(f'<td><a href="file://{file}">{len(session.active_cases())}</a></td>')
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)
        fh.write("</tr>\n")
        fh.write("</table>\n</body>\n</html>")

    def generate_group_index(self, cases, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        key = "Defective" if cases[0].defective() else cases[0].status.name
        fh.write(f"<body>\n<h1> {key} Summary </h1>\n")
        fh.write('<table class="sortable">\n')
        fh.write("<thead><tr><th>Test</th><th>Duration</th><th>Status</th></tr></thead>\n")
        fh.write("<tbody>")
        for case in sorted(cases, key=lambda c: c.duration):
            file = os.path.join(self.cases_dir, f"{case.id}.html")
            if not os.path.exists(file):
                raise ValueError(f"{file}: html file not found")
            link = f'<a href="file://{file}">{case.display_name}</a>'
            html_name = "Defective" if case.defective() else case.status.html_name
            fh.write(f"<tr><td>{link}</td><td>{case.duration:.2f}</td><td>{html_name}</td></tr>\n")
        fh.write("</tbody>")
        fh.write("</table>\n</body>\n</html>")

    def generate_all_tests_index(self, totals: dict, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Test Results</h1>\n<table>\n")
        fh.write("<tr><th>Test</th><th>Duration</th><th>Status</th></tr>\n")
        for group, cases in totals.items():
            for case in sorted(cases, key=lambda c: c.duration):
                file = os.path.join(self.cases_dir, f"{case.id}.html")
                if not os.path.exists(file):
                    raise ValueError(f"{file}: html file not found")
                link = f'<a href="file://{file}">{case.display_name}</a>'
                html_name = "Defective" if case.defective() else case.status.html_name
                fh.write(
                    f"<tr><td>{link}</td><td>{case.duration:.2f}</td><td>{html_name}</td></tr>\n"
                )
        fh.write("</table>\n</body>\n</html>")
