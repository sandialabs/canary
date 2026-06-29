# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import html
import os
from argparse import Namespace
from pathlib import Path
from typing import TYPE_CHECKING
from typing import TextIO

from ... import config
from ...hookspec import hookimpl
from ...util import json_helper as json
from ...util import logging
from ...util.filesystem import force_remove
from ...util.filesystem import mkdirp
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...job import Job
    from ...view import ViewManifestEntry
    from ...view import ViewReportRequest
    from ...workspace import Workspace

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class HTMLReportRequest:
    """Inputs required to render an HTML report.

    This request is intentionally not tied to a view.  View lifecycle reporting
    and the standalone `canary report html` command both adapt their context
    into this renderer request.
    """

    workspace: "Workspace"
    jobs: list["Job"]
    output_dir: Path


@hookimpl
def canary_reporter() -> CanaryReporter:
    return HTMLReportCommand()


@hookimpl
def canary_view_report(request: "ViewReportRequest") -> None:
    """Create an HTML report for a completed view snapshot."""
    if "html" not in request.formats:
        return

    reporter = HTMLReporter()
    jobs = reporter.load_view_jobs(request)

    output_root = request.output_dir or request.view.metadata_dir / "reports"
    output_dir = output_root / "html"

    html_request = HTMLReportRequest(
        workspace=request.workspace,
        jobs=jobs,
        output_dir=output_dir,
    )

    entrypoint = reporter.write(html_request)
    link_summary(request.view.dir / "summary.html", entrypoint)


class HTMLReportCommand(CanaryReporter):
    type = "html"
    description = "HTML reporter"

    def setup_parser(self, parser) -> None:
        parser.add_argument(
            "-o",
            "--output-dir",
            default="HTML",
            help="Output directory [default: %(default)s]",
        )

    def run_from_args(self, args: Namespace) -> int:
        from ...workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()

        request = HTMLReportRequest(
            workspace=workspace,
            jobs=jobs,
            output_dir=Path(args.output_dir).absolute(),
        )

        HTMLReporter().write(request)
        return 0


class HTMLReporter:
    """HTML renderer for Canary reports."""

    type = "html"
    description = "HTML reporter"

    def write(self, request: HTMLReportRequest) -> Path:
        """Write an HTML report and return its entry point."""
        final_dir = request.output_dir
        tmp_dir = final_dir.with_name(f".{final_dir.name}.tmp-{os.getpid()}")

        force_remove(tmp_dir)
        mkdirp(tmp_dir / "jobs")

        try:
            self.write_report(
                jobs=request.jobs,
                html_dir=tmp_dir,
                jobs_dir=tmp_dir / "jobs",
                index=tmp_dir / "index.html",
            )

            force_remove(final_dir)
            os.rename(tmp_dir, final_dir)

        except Exception:
            force_remove(tmp_dir)
            raise

        entrypoint = final_dir / "index.html"
        rel = os.path.relpath(entrypoint, config.invocation_dir)
        logger.info(f"HTML report written to {rel}")
        return entrypoint

    def load_view_jobs(self, request: "ViewReportRequest") -> list["Job"]:
        """Load jobs represented by the current view manifest.

        The manifest is treated as authoritative for the view snapshot.
        """
        manifest = request.view.load_manifest()
        jobs: list["Job"] = []

        for entry in manifest.entries.values():
            job = self.load_job_from_entry(entry)
            if job is not None:
                jobs.append(job)

        return jobs

    def load_job_from_entry(self, entry: "ViewManifestEntry") -> "Job | None":
        lockfile = Path(entry.source) / "testcase.lock"
        if not lockfile.exists():
            logger.warning(f"{lockfile}: testcase lock not found; skipping report entry")
            return None
        try:
            return json.loads(lockfile.read_text())
        except Exception:
            logger.exception(f"{lockfile}: failed to load testcase lock")
            return None

    def write_report(
        self,
        *,
        jobs: list["Job"],
        html_dir: Path,
        jobs_dir: Path,
        index: Path,
    ) -> None:
        for job in jobs:
            file = jobs_dir / f"{job.id}.html"
            with open(file, "w") as fh:
                self.generate_case_file(job, fh)

        with open(index, "w") as fh:
            self.generate_index(jobs, html_dir=html_dir, jobs_dir=jobs_dir, index=index, fh=fh)

    @property
    def style(self) -> str:
        return """\
<style>
body {
  font-family: Arial, sans-serif;
  margin: 2rem;
}
table {
  font-family: Arial, sans-serif;
  border-collapse: collapse;
}
td, th {
  border: 1px solid #dddddd;
  text-align: left;
  padding: 8px;
}
tr:nth-child(even) {
  background-color: #eeeeee;
}
pre {
  background: #f6f8fa;
  border: 1px solid #dddddd;
  padding: 1rem;
  overflow-x: auto;
}
.code {
  font-family: monospace;
}
</style>
"""

    @property
    def head(self) -> str:
        return f'<head>\n<meta charset="utf-8">\n{self.style}\n</head>\n'

    def generate_case_file(self, job: "Job", fh: TextIO) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body>\n")
        fh.write(f"<h1>{html.escape(job.display_name())}</h1>\n")
        fh.write("<table>\n")
        self.write_info_row(fh, "Test", job.display_name())
        self.write_info_row(fh, "Status", str(job.status.outcome))
        self.write_info_row(fh, "Exit code", str(job.status.code))
        self.write_info_row(fh, "ID", job.id)
        self.write_info_row(fh, "Location", str(job.workspace.dir))
        self.write_info_row(fh, "Duration", f"{job.timekeeper.duration():.4f}")
        fh.write("</table>\n")

        fh.write("<h2>Test output</h2>\n<pre>\n")
        try:
            fh.write(html.escape(job.read_output()))
        except Exception:
            logger.exception(f"Failed reading output for job {job.id}")
            fh.write("Failed to read test output.")
        fh.write("\n</pre>\n")

        fh.write("</body>\n</html>\n")

    def write_info_row(self, fh: TextIO, key: str, value: str) -> None:
        fh.write(f"<tr><td><b>{html.escape(key)}</b></td><td>{html.escape(value)}</td></tr>\n")

    def generate_index(
        self,
        jobs: list["Job"],
        *,
        html_dir: Path,
        jobs_dir: Path,
        index: Path,
        fh: TextIO,
    ) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Canary Summary</h1>\n")

        totals: dict[str, list["Job"]] = {}
        for job in jobs:
            group = self.report_group(job)
            totals.setdefault(group, []).append(job)

        fh.write("<table>\n<tr>")
        for col in (
            "Site",
            "Project",
            "Not Run",
            "Timeout",
            "Fail",
            "Diff",
            "Success",
            "Invalid",
            "Cancelled",
            "Total",
        ):
            fh.write(f"<th>{html.escape(col)}</th>")
        fh.write("</tr>\n<tr>")

        fh.write(f"<td>{html.escape(os.uname().nodename)}</td>")
        fh.write(f"<td>{html.escape(str(config.get('cmake:project') or ''))}</td>")

        for group in ("Not Run", "Timeout", "Fail", "Diff", "Success", "Invalid", "Cancelled"):
            group_jobs = totals.get(group, [])
            if not group_jobs:
                fh.write("<td>0</td>")
                continue

            file = html_dir / f"{''.join(group.split())}.html"
            self.generate_group_index_file(group_jobs, file=file, jobs_dir=jobs_dir)
            href = self.href(index, file)
            fh.write(f'<td><a href="{href}">{len(group_jobs)}</a></td>')

        total_file = html_dir / "Total.html"
        self.generate_all_tests_index_file(totals, file=total_file, jobs_dir=jobs_dir)
        href = self.href(index, total_file)
        fh.write(f'<td><a href="{href}">{len(jobs)}</a></td>')

        fh.write("</tr>\n</table>\n</body>\n</html>\n")

    def generate_group_index_file(
        self,
        jobs: list["Job"],
        *,
        file: Path,
        jobs_dir: Path,
    ) -> None:
        with open(file, "w") as fh:
            self.generate_group_index(jobs, file=file, jobs_dir=jobs_dir, fh=fh)

    def generate_group_index(
        self,
        jobs: list["Job"],
        *,
        file: Path,
        jobs_dir: Path,
        fh: TextIO,
    ) -> None:
        key = jobs[0].status.outcome

        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write(f"<body>\n<h1>{html.escape(str(key))} Summary</h1>\n")
        fh.write("<table>\n")
        fh.write(
            "<thead><tr><th>Test</th><th>ID</th><th>Duration</th><th>Status</th></tr></thead>\n"
        )
        fh.write("<tbody>\n")

        for job in sorted(jobs, key=lambda c: c.timekeeper.duration()):
            job_file = jobs_dir / f"{job.id}.html"
            if not job_file.exists():
                raise ValueError(f"{job_file}: html file not found")

            link = self.job_link(from_file=file, job_file=job_file, job=job)
            status = job.status.display_name(style="html")
            fh.write(
                "<tr>"
                f"<td>{link}</td>"
                f'<td class="code">{html.escape(job.id[:7])}</td>'
                f"<td>{job.timekeeper.duration():.2f}</td>"
                f"<td>{status}</td>"
                "</tr>\n"
            )

        fh.write("</tbody>\n</table>\n</body>\n</html>\n")

    def generate_all_tests_index_file(
        self,
        totals: dict[str, list["Job"]],
        *,
        file: Path,
        jobs_dir: Path,
    ) -> None:
        with open(file, "w") as fh:
            self.generate_all_tests_index(totals, file=file, jobs_dir=jobs_dir, fh=fh)

    def generate_all_tests_index(
        self,
        totals: dict[str, list["Job"]],
        *,
        file: Path,
        jobs_dir: Path,
        fh: TextIO,
    ) -> None:
        fh.write("<!doctype html>\n<html>\n")
        fh.write(self.head)
        fh.write("<body>\n<h1>Test Results</h1>\n<table>\n")
        fh.write("<tr><th>Test</th><th>ID</th><th>Duration</th><th>Status</th></tr>\n")

        for _, jobs in totals.items():
            for job in sorted(jobs, key=lambda c: c.timekeeper.duration()):
                job_file = jobs_dir / f"{job.id}.html"
                if not job_file.exists():
                    raise ValueError(f"{job_file}: html file not found")

                link = self.job_link(from_file=file, job_file=job_file, job=job)
                status = job.status.display_name(style="html")
                fh.write(
                    "<tr>"
                    f"<td>{link}</td>"
                    f'<td class="code">{html.escape(job.id[:7])}</td>'
                    f"<td>{job.timekeeper.duration():.2f}</td>"
                    f"<td>{status}</td>"
                    "</tr>\n"
                )

        fh.write("</table>\n</body>\n</html>\n")

    def job_link(self, *, from_file: Path, job_file: Path, job: "Job") -> str:
        href = self.href(from_file, job_file)
        text = html.escape(job.display_name())
        return f'<a href="{href}">{text}</a>'

    def href(self, from_file: Path, to_file: Path) -> str:
        return html.escape(os.path.relpath(to_file, from_file.parent), quote=True)

    def report_group(self, job: "Job") -> str:
        outcome = job.status.outcome.name

        if outcome == "NONE":
            return "Not Run"
        if outcome == "SUCCESS":
            return "Success"
        if outcome == "TIMEOUT":
            return "Timeout"
        if outcome == "DIFFED":
            return "Diff"
        if outcome == "FAILED":
            return "Fail"
        if outcome == "INVALID":
            return "Invalid"
        if outcome in {"CANCELLED", "INTERRUPTED"}:
            return "Cancelled"

        # Reasonable defaults for current status model:
        if outcome in {"ERROR", "BROKEN"}:
            return "Fail"
        if outcome in {"XFAIL", "XDIFF"}:
            return "Success"
        if outcome in {"SKIPPED", "BLOCKED"}:
            return "Not Run"

        return outcome.title()


def link_summary(summary: Path, entrypoint: Path) -> None:
    """Create or replace a view-level summary.html symlink."""
    target = os.path.relpath(entrypoint, summary.parent)

    if summary.is_symlink() or summary.is_file():
        summary.unlink()
    elif summary.exists():
        raise ValueError(f"{summary}: exists and is not a file or symlink")

    summary.symlink_to(target)
