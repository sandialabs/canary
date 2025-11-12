# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import string
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from ... import config
from ...util import logging
from ...util.filesystem import force_remove
from ...util.filesystem import mkdirp
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...testcase import TestCase

logger = logging.get_logger(__name__)


@hookimpl
def canary_session_reporter() -> CanaryReporter:
    return HTMLReporter()


class HTMLReporter(CanaryReporter):
    type = "html"
    description = "HTML reporter"
    multipage = True

    def create(self, **kwargs: Any) -> None:
        workspace = Workspace.load()
        cases = workspace.load_testcases()
        work_tree = workspace.view or workspace.sessions_dir
        dest = string.Template(kwargs["dest"]).safe_substitute(canary_work_tree=str(work_tree))
        self.html_dir = os.path.join(dest, "HTML")
        self.cases_dir = os.path.join(self.html_dir, "cases")
        self.index = os.path.join(dest, "canary-report.html")

        force_remove(self.html_dir)
        mkdirp(self.cases_dir)
        for case in cases:
            file = os.path.join(self.cases_dir, f"{case.id}.html")
            with open(file, "w") as fh:
                self.generate_case_file(case, fh)
        with open(self.index, "w") as fh:
            self.generate_index(cases, fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logger.info(f"HTML report written to {f}")

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

    def generate_case_file(self, case: "TestCase", fh: TextIO) -> None:
        if case.mask:
            return
        fh.write("<html>\n")
        fh.write("<body>\n<table>\n")
        fh.write(f"<tr><td><b>Test:</b> {case.display_name}</td></tr>\n")
        fh.write(f"<tr><td><b>Status:</b> {case.status.name}</td></tr>\n")
        fh.write(f"<tr><td><b>Exit code:</b> {case.status.code}</td></tr>\n")
        fh.write(f"<tr><td><b>ID:</b> {case.id}</td></tr>\n")
        fh.write(f"<tr><td><b>Duration:</b> {case.timekeeper.duration}</td></tr>\n")
        fh.write("</table>\n")
        fh.write("<h2>Test output</h2>\n<pre>\n")
        fh.write(case.read_output())
        fh.write("</pre>\n</body>\n</html>\n")

    def generate_index(self, cases: list["TestCase"], fh: TextIO) -> None:
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
            "Invalid",
            "Cancelled",
            "Total",
        ):
            fh.write(f"<th>{col}</th>")
        fh.write("</tr>\n")
        totals: dict[str, list["TestCase"]] = {}
        for case in cases:
            group = case.status.name.title()
            totals.setdefault(group, []).append(case)
        fh.write("<tr>")
        fh.write(f"<td>{config.get('system:host')}</td>")
        fh.write(f"<td>{config.get('build:project')}</td>")
        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Invalid", "Cancelled"):
            if group not in totals:
                fh.write("<td>0</td>")
            else:
                n = len(totals[group])
                file = os.path.join(self.html_dir, "%s.html" % "".join(group.split()))
                fh.write(f'<td><a href="file://{file}">{n}</a></td>')
                with open(file, "w") as fp:
                    self.generate_group_index(totals[group], fp)
        file = os.path.join(self.html_dir, "Total.html")
        fh.write(f'<td><a href="file://{file}">{len(cases)}</a></td>')
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)
        fh.write("</tr>\n")
        fh.write("</table>\n</body>\n</html>")

    def generate_group_index(self, cases, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        key = cases[0].status.name
        fh.write(f"<body>\n<h1> {key} Summary </h1>\n")
        fh.write('<table class="sortable">\n')
        fh.write("<thead><tr><th>Test</th><th>Duration</th><th>Status</th></tr></thead>\n")
        fh.write("<tbody>")
        for case in sorted(cases, key=lambda c: c.duration):
            file = os.path.join(self.cases_dir, f"{case.id}.html")
            if not os.path.exists(file):
                raise ValueError(f"{file}: html file not found")
            link = f'<a href="file://{file}">{case.display_name}</a>'
            html_name = case.status.html_name
            fh.write(
                f"<tr><td>{link}</td><td>{case.timekeeper.duration:.2f}</td><td>{html_name}</td></tr>\n"
            )
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
                html_name = case.status.html_name
                fh.write(
                    f"<tr><td>{link}</td><td>{case.timekeeper.duration:.2f}</td><td>{html_name}</td></tr>\n"
                )
        fh.write("</table>\n</body>\n</html>")
