# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
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
    from ...config.argparsing import Parser
    from ...job import Job
    from ...view import ViewManifestEntry
    from ...view import ViewReportRequest
    from ...workspace import Workspace

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class MarkdownReportRequest:
    """Inputs required to render a Markdown report.

    This request is intentionally not tied to a view. View lifecycle reporting
    and the standalone `canary report markdown` command both adapt their
    context into this renderer request.
    """

    workspace: "Workspace"
    jobs: list["Job"]
    output_dir: Path


@hookimpl
def canary_reporter() -> CanaryReporter:
    return MarkdownReportCommand()


@hookimpl
def canary_view_report(request: "ViewReportRequest") -> None:
    """Create a Markdown report for a completed view snapshot."""
    if "markdown" not in request.formats:
        return

    reporter = MarkdownReporter()
    jobs = reporter.load_view_jobs(request)

    output_root = request.output_dir or request.view.metadata_dir / "reports"
    output_dir = output_root / "markdown"

    markdown_request = MarkdownReportRequest(
        workspace=request.workspace, jobs=jobs, output_dir=output_dir
    )

    reporter.write(markdown_request)


class MarkdownReportCommand(CanaryReporter):
    type = "markdown"
    description = "Markdown reporter"

    def setup_parser(self, parser: "Parser") -> None:
        # Compatibility positional:
        #
        #   canary report markdown create
        #
        # The preferred spelling is:
        #
        #   canary report markdown
        #
        parser.add_argument(
            "_create", nargs="?", choices=("create",), metavar="", help=argparse.SUPPRESS
        )
        parser.add_argument(
            "-o", "--output-dir", default="MARKDOWN", help="Output directory [default: %(default)s]"
        )
        parser.set_defaults(_markdown_report_handler=self.run_create)

    def run_from_args(self, args: Namespace) -> int:
        handler = getattr(args, "_markdown_report_handler", None)
        if handler is None:
            raise ValueError("canary report markdown: missing action")
        handler(args)
        return 0

    def run_create(self, args: Namespace) -> None:
        from ...workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        output_dir = Path(args.output_dir).absolute()
        request = MarkdownReportRequest(workspace=workspace, jobs=jobs, output_dir=output_dir)
        MarkdownReporter().write(request)


class MarkdownReporter:
    """Markdown renderer for Canary reports."""

    type = "markdown"
    description = "Markdown reporter"

    def write(self, request: MarkdownReportRequest) -> Path:
        """Write a Markdown report and return its entry point."""
        final_dir = request.output_dir
        tmp_dir = final_dir.with_name(f".{final_dir.name}.tmp-{os.getpid()}")

        force_remove(tmp_dir)
        mkdirp(tmp_dir)

        try:
            self.write_report(jobs=request.jobs, md_dir=tmp_dir, index=tmp_dir / "index.md")

            force_remove(final_dir)
            os.rename(tmp_dir, final_dir)

        except Exception:
            force_remove(tmp_dir)
            raise

        entrypoint = final_dir / "index.md"
        rel = os.path.relpath(entrypoint, config.invocation_dir)
        logger.info(f"Markdown report written to {rel}")
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

    def write_report(self, *, jobs: list["Job"], md_dir: Path, index: Path) -> None:
        for job in jobs:
            file = md_dir / f"{job.id}.md"
            with open(file, "w") as fh:
                try:
                    self.generate_case_file(job, fh)
                except Exception:
                    logger.exception(f"Issue writing report for test job ID: {job.id}")

        with open(index, "w") as fh:
            self.generate_index(jobs, md_dir=md_dir, index=index, fh=fh)

    def generate_case_file(self, job: "Job", fh: TextIO) -> None:
        fh.write(f"# {escape_markdown_text(job.display_name())}\n\n")
        self.render_test_info_table(job, fh)
        fh.write("## Test output\n\n")

        output = job.read_output()
        fence = code_fence_for(output)
        fh.write(f"{fence}console\n")
        fh.write(output)
        if output and not output.endswith("\n"):
            fh.write("\n")
        fh.write(f"{fence}\n\n")

    def render_test_info_table(self, job: "Job", fh: TextIO) -> None:
        info: dict[str, str] = {
            "Status": job.status.outcome.name,
            "Exit code": str(job.status.code),
            "ID": str(job.id),
            "Location": str(job.workspace.dir),
            "Duration": f"{job.timekeeper.duration():.4f}",
        }

        fh.write("| | |\n")
        fh.write("| --- | --- |\n")
        for key, val in info.items():
            fh.write(f"| **{escape_table_cell(key)}** | {escape_table_cell(val)} |\n")
        fh.write("\n")

    def generate_index(self, jobs: list["Job"], *, md_dir: Path, index: Path, fh: TextIO) -> None:
        fh.write("# Canary Summary\n\n")
        fh.write(
            "| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Invalid | Cancelled | Total |\n"
        )
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")

        totals: dict[str, list["Job"]] = {}
        for job in jobs:
            group = self.report_group(job)
            totals.setdefault(group, []).append(job)

        fh.write(f"| {escape_table_cell(os.uname().nodename)} ")
        fh.write(f"| {escape_table_cell(str(config.get('cmake:project') or ''))} ")

        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Invalid", "Cancelled"):
            group_jobs = totals.get(group, [])
            if not group_jobs:
                fh.write("| 0 ")
                continue

            file = md_dir / f"{''.join(group.split())}.md"
            relpath = os.path.relpath(file, index.parent)
            fh.write(f"| [{len(group_jobs)}]({escape_link_target(relpath)}) ")

            with open(file, "w") as fp:
                self.generate_group_index(group_jobs, file=file, md_dir=md_dir, fh=fp)

        total_file = md_dir / "Total.md"
        relpath = os.path.relpath(total_file, index.parent)
        fh.write(f"| [{len(jobs)}]({escape_link_target(relpath)}) |\n")

        with open(total_file, "w") as fp:
            self.generate_all_tests_index(totals, file=total_file, md_dir=md_dir, fh=fp)

    def report_group(self, job: "Job") -> str:
        """Map internal outcomes to stable Markdown summary groups."""
        outcome = job.status.outcome.name

        if outcome == "NONE":
            return "Not Run"
        if outcome == "SUCCESS":
            return "Pass"
        if outcome in {"XFAIL", "XDIFF"}:
            return "Pass"
        if outcome == "TIMEOUT":
            return "Timeout"
        if outcome == "DIFFED":
            return "Diff"
        if outcome in {"FAILED", "ERROR", "BROKEN"}:
            return "Fail"
        if outcome == "INVALID":
            return "Invalid"
        if outcome in {"CANCELLED", "INTERRUPTED"}:
            return "Cancelled"
        if outcome in {"SKIPPED", "BLOCKED"}:
            return "Not Run"

        return outcome.title()

    def generate_group_index(
        self, jobs: list["Job"], *, file: Path, md_dir: Path, fh: TextIO
    ) -> None:
        group = self.report_group(jobs[0])

        fh.write(f"# {escape_markdown_text(group)} Summary\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")

        for job in sorted(jobs, key=lambda c: c.name.lower()):
            job_file = md_dir / f"{job.id}.md"
            if not job_file.exists():
                raise ValueError(f"{job_file}: markdown file not found")

            relpath = os.path.relpath(job_file, file.parent)
            link = f"[{escape_link_text(job.display_name())}]({escape_link_target(relpath)})"
            duration = f"{job.timekeeper.duration():.2f}"
            outcome = job.status.outcome.name
            fh.write(
                f"| {link} | {escape_table_cell(job.id)} | "
                f"{escape_table_cell(duration)} | {escape_table_cell(outcome)} |\n"
            )

    def generate_all_tests_index(
        self, totals: dict[str, list["Job"]], *, file: Path, md_dir: Path, fh: TextIO
    ) -> None:
        fh.write("# Test Results\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")

        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Invalid", "Cancelled"):
            for job in sorted(totals.get(group, []), key=lambda c: c.timekeeper.duration()):
                job_file = md_dir / f"{job.id}.md"
                if not job_file.exists():
                    raise ValueError(f"{job_file}: markdown file not found")

                relpath = os.path.relpath(job_file, file.parent)
                link = f"[{escape_link_text(job.display_name())}]({escape_link_target(relpath)})"
                duration = f"{job.timekeeper.duration():.2f}"
                outcome = job.status.outcome.name
                fh.write(
                    f"| {link} | {escape_table_cell(job.id)} | "
                    f"{escape_table_cell(duration)} | {escape_table_cell(outcome)} |\n"
                )

        fh.write("\n")


def escape_table_cell(value: str) -> str:
    return (
        str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>").replace("\r", "")
    )


def escape_markdown_text(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", " ")


def escape_link_text(value: str) -> str:
    return str(value).replace("[", "\\[").replace("]", "\\]").replace("\n", " ")


def escape_link_target(value: str) -> str:
    return str(value).replace(" ", "%20").replace(")", "%29")


def code_fence_for(text: str) -> str:
    longest = 0
    current = 0

    for ch in text:
        if ch == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return "`" * max(3, longest + 1)
