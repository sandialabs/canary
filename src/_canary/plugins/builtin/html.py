# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import string
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

from ... import config
from ...hookspec import hookimpl
from ...util import logging
from ...util.filesystem import force_remove
from ...util.filesystem import mkdirp
from ...workspace import Workspace
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...job import Job

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
        jobs = workspace.load_jobs()
        work_tree: Path
        if view := workspace.latest_view():
            work_tree = view.dir
        else:
            work_tree = workspace.sessions_dir
        dest = string.Template(kwargs["dest"]).safe_substitute(canary_work_tree=str(work_tree))
        self.html_dir = os.path.join(dest, "HTML")
        self.jobs_dir = os.path.join(self.html_dir, "jobs")
        self.index = os.path.join(dest, "canary-report.html")

        force_remove(self.html_dir)
        mkdirp(self.jobs_dir)
        for job in jobs:
            file = os.path.join(self.jobs_dir, f"{job.id}.html")
            with open(file, "w") as fh:
                self.generate_case_file(job, fh)
        with open(self.index, "w") as fh:
            self.generate_index(jobs, fh)
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

    def generate_case_file(self, job: "Job", fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write("<body>\n<table>\n")
        fh.write(f"<tr><td><b>Test:</b> {job.display_name()}</td></tr>\n")
        fh.write(f"<tr><td><b>Status:</b> {job.status.outcome}</td></tr>\n")
        fh.write(f"<tr><td><b>Exit code:</b> {job.status.code}</td></tr>\n")
        fh.write(f"<tr><td><b>ID:</b> {job.id}</td></tr>\n")
        fh.write(f"<tr><td><b>Duration:</b> {job.timekeeper.duration()}</td></tr>\n")
        fh.write("</table>\n")
        fh.write("<h2>Test output</h2>\n<pre>\n")
        fh.write(job.read_output())
        fh.write("</pre>\n</body>\n</html>\n")

    def generate_index(self, jobs: list["Job"], fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Canary Summary</h1>\n")
        fh.write("<table>\n<tr>")
        for col in (
            "Site",
            "Project",
            "Not Run",
            "Timeout",
            "Failed",
            "Diffed",
            "Success",
            "Invalid",
            "Cancelled",
            "Total",
        ):
            fh.write(f"<th>{col}</th>")
        fh.write("</tr>\n")
        totals: dict[str, list["Job"]] = {}
        for job in jobs:
            group = job.status.outcome.name.title()
            totals.setdefault(group, []).append(job)
        fh.write("<tr>")
        fh.write(f"<td>{os.uname().nodename}</td>")
        fh.write(f"<td>{config.get('cmake:project')}</td>")
        for group in ("Not Run", "Timeout", "Fail", "Diffed", "Success", "Invalid", "Cancelled"):
            if group not in totals:
                fh.write("<td>0</td>")
            else:
                n = len(totals[group])
                file = os.path.join(self.html_dir, "%s.html" % "".join(group.split()))
                fh.write(f'<td><a href="file://{file}">{n}</a></td>')
                with open(file, "w") as fp:
                    self.generate_group_index(totals[group], fp)
        file = os.path.join(self.html_dir, "Total.html")
        fh.write(f'<td><a href="file://{file}">{len(jobs)}</a></td>')
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)
        fh.write("</tr>\n")
        fh.write("</table>\n</body>\n</html>")

    def generate_group_index(self, jobs, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        key = jobs[0].status.outcome
        fh.write(f"<body>\n<h1> {key} Summary </h1>\n")
        fh.write('<table class="sortable">\n')
        fh.write("<thead><tr><th>Test</th><th>Duration</th><th>Status</th></tr></thead>\n")
        fh.write("<tbody>")
        for job in sorted(jobs, key=lambda c: c.timekeeper.duration()):
            file = os.path.join(self.jobs_dir, f"{job.id}.html")
            if not os.path.exists(file):
                raise ValueError(f"{file}: html file not found")
            link = f'<a href="file://{file}">{job.display_name()}</a>'
            html_name = job.status.display_name(style="html")
            fh.write(
                f"<tr><td>{link}</td><td>{job.timekeeper.duration():.2f}</td><td>{html_name}</td></tr>\n"
            )
        fh.write("</tbody>")
        fh.write("</table>\n</body>\n</html>")

    def generate_all_tests_index(self, totals: dict, fh: TextIO) -> None:
        fh.write("<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Test Results</h1>\n<table>\n")
        fh.write("<tr><th>Test</th><th>Duration</th><th>Status</th></tr>\n")
        for group, jobs in totals.items():
            for job in sorted(jobs, key=lambda c: c.timekeeper.duration()):
                file = os.path.join(self.jobs_dir, f"{job.id}.html")
                if not os.path.exists(file):
                    raise ValueError(f"{file}: html file not found")
                link = f'<a href="file://{file}">{job.display_name()}</a>'
                html_name = job.status.display_name(style="html")
                fh.write(
                    f"<tr><td>{link}</td><td>{job.timekeeper.duration():.2f}</td><td>{html_name}</td></tr>\n"
                )
        fh.write("</table>\n</body>\n</html>")
