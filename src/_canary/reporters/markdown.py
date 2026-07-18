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

from .. import config
from ..hookspec import hookimpl
from ..util import json_helper as json
from ..util import logging
from ..util.filesystem import mkdirp
from .reporter import CanaryReporter
from .reporter import enabled

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..job import Job
    from ..runtest import Runner
    from ..workspace import Workspace

logger = logging.get_logger(__name__)

MANIFEST = "manifest.json"


@dataclasses.dataclass
class MarkdownReportRequest:
    workspace: "Workspace"
    jobs: list["Job"]
    output_dir: Path


@dataclasses.dataclass
class MarkdownReportRecord:
    id: str
    name: str
    display_name: str
    status: str
    group: str
    code: int
    reason: str
    duration: float
    session: str | None
    workspace: str
    page: str

    @classmethod
    def from_job(cls, job: "Job", reporter: "MarkdownReporter") -> "MarkdownReportRecord":
        return cls(
            id=job.id,
            name=job.name,
            display_name=job.display_name(),
            status=job.status.outcome.name,
            group=reporter.report_group(job),
            code=job.status.code,
            reason=job.status.reason or "",
            duration=job.timekeeper.duration(),
            session=job.workspace.session,
            workspace=str(job.workspace.dir),
            page=f"{job.id}.md",
        )


@hookimpl
def canary_reporter() -> CanaryReporter:
    return MarkdownReportCommand()


@hookimpl(trylast=True)
def canary_runtests_report(runner: "Runner") -> None:
    """Create or update a Markdown report for completed jobs."""
    if not enabled("markdown"):
        return

    ws = runner.workspace
    reporter = MarkdownReporter()
    markdown_request = MarkdownReportRequest(
        workspace=ws, jobs=runner.jobs, output_dir=ws.reports_dir / "markdown"
    )
    entrypoint = reporter.write(markdown_request)
    link = link_summary(runner.workspace.root.parent / "Canary.md", entrypoint)
    rel = os.path.relpath(link, config.invocation_dir)
    logger.info(f"Markdown report written to {rel}")


class MarkdownReportCommand(CanaryReporter):
    type = "markdown"
    description = "Markdown reporter"

    def setup_parser(self, parser: "Parser") -> None:
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
        from ..workspace import Workspace

        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        output_dir = Path(args.output_dir).absolute()
        request = MarkdownReportRequest(workspace=workspace, jobs=jobs, output_dir=output_dir)
        MarkdownReporter().write(request)


class MarkdownReporter:
    type = "markdown"
    description = "Markdown reporter"

    group_order = ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Invalid", "Cancelled")

    def write(self, request: MarkdownReportRequest) -> Path:
        """Update a Markdown report in place and return its entry point."""
        final_dir = request.output_dir
        mkdirp(final_dir)

        records = load_manifest(final_dir)

        for job in request.jobs:
            record = MarkdownReportRecord.from_job(job, self)
            records[job.id] = record

            page = final_dir / record.page
            tmp = page.with_name(f".{page.name}.tmp-{os.getpid()}")
            try:
                with open(tmp, "w") as fh:
                    self.generate_case_file(job, fh)
                os.replace(tmp, page)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise

        save_manifest(final_dir, records)
        self.write_index_files(records, md_dir=final_dir)

        entrypoint = final_dir / "index.md"
        return entrypoint

    def write_index_files(self, records: dict[str, MarkdownReportRecord], *, md_dir: Path) -> None:
        all_records = list(records.values())

        totals: dict[str, list[MarkdownReportRecord]] = {}
        for record in all_records:
            totals.setdefault(record.group, []).append(record)

        index = md_dir / "index.md"
        tmp = index.with_name(f".{index.name}.tmp-{os.getpid()}")

        try:
            with open(tmp, "w") as fh:
                self.generate_index_records(
                    all_records, totals=totals, md_dir=md_dir, index=index, fh=fh
                )
            os.replace(tmp, index)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        for group in self.group_order:
            file = md_dir / f"{''.join(group.split())}.md"
            group_records = totals.get(group, [])
            if group_records:
                self.write_group_index_records(group_records, file=file, md_dir=md_dir)
            else:
                file.unlink(missing_ok=True)

        total_file = md_dir / "Total.md"
        self.write_all_tests_index_records(totals, file=total_file, md_dir=md_dir)

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

        if job.status.reason:
            info["Reason"] = job.status.reason

        fh.write("| | |\n")
        fh.write("| --- | --- |\n")
        for key, val in info.items():
            fh.write(f"| **{escape_table_cell(key)}** | {escape_table_cell(val)} |\n")
        fh.write("\n")

    def generate_index_records(
        self,
        records: list[MarkdownReportRecord],
        *,
        totals: dict[str, list[MarkdownReportRecord]],
        md_dir: Path,
        index: Path,
        fh: TextIO,
    ) -> None:
        fh.write("# Canary Summary\n\n")
        fh.write(
            "| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Invalid | Cancelled | Total |\n"
        )
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")

        fh.write(f"| {escape_table_cell(os.uname().nodename)} ")
        fh.write(f"| {escape_table_cell(str(config.get('cmake:project') or ''))} ")

        for group in self.group_order:
            group_records = totals.get(group, [])
            if not group_records:
                fh.write("| 0 ")
                continue

            file = md_dir / f"{''.join(group.split())}.md"
            relpath = os.path.relpath(file, index.parent)
            fh.write(f"| [{len(group_records)}]({escape_link_target(relpath)}) ")

        total_file = md_dir / "Total.md"
        relpath = os.path.relpath(total_file, index.parent)
        fh.write(f"| [{len(records)}]({escape_link_target(relpath)}) |\n")

    def report_group(self, job: "Job") -> str:
        outcome = job.status.outcome.name

        if outcome == "NONE":
            return "Not Run"
        if outcome in {"SUCCESS", "XFAIL", "XDIFF"}:
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

    def write_group_index_records(
        self, records: list[MarkdownReportRecord], *, file: Path, md_dir: Path
    ) -> None:
        tmp = file.with_name(f".{file.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                self.generate_group_index_records(records, file=file, md_dir=md_dir, fh=fh)
            os.replace(tmp, file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def generate_group_index_records(
        self, records: list[MarkdownReportRecord], *, file: Path, md_dir: Path, fh: TextIO
    ) -> None:
        group = records[0].group

        fh.write(f"# {escape_markdown_text(group)} Summary\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")

        for record in sorted(records, key=lambda r: r.name.lower()):
            link = self.record_link(from_file=file, md_dir=md_dir, record=record)
            duration = f"{record.duration:.2f}"
            fh.write(
                f"| {link} | {escape_table_cell(record.id)} | "
                f"{escape_table_cell(duration)} | {escape_table_cell(record.status)} |\n"
            )

        fh.write("\n")

    def write_all_tests_index_records(
        self, totals: dict[str, list[MarkdownReportRecord]], *, file: Path, md_dir: Path
    ) -> None:
        tmp = file.with_name(f".{file.name}.tmp-{os.getpid()}")
        try:
            with open(tmp, "w") as fh:
                self.generate_all_tests_index_records(totals, file=file, md_dir=md_dir, fh=fh)
            os.replace(tmp, file)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def generate_all_tests_index_records(
        self, totals: dict[str, list[MarkdownReportRecord]], *, file: Path, md_dir: Path, fh: TextIO
    ) -> None:
        fh.write("# Test Results\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")

        for group in self.group_order:
            for record in sorted(totals.get(group, []), key=lambda r: r.duration):
                link = self.record_link(from_file=file, md_dir=md_dir, record=record)
                duration = f"{record.duration:.2f}"
                fh.write(
                    f"| {link} | {escape_table_cell(record.id)} | "
                    f"{escape_table_cell(duration)} | {escape_table_cell(record.status)} |\n"
                )

        fh.write("\n")

    def record_link(self, *, from_file: Path, md_dir: Path, record: MarkdownReportRecord) -> str:
        target = md_dir / record.page
        relpath = os.path.relpath(target, from_file.parent)
        return f"[{escape_link_text(record.display_name)}]({escape_link_target(relpath)})"


def load_manifest(report_dir: Path) -> dict[str, MarkdownReportRecord]:
    path = report_dir / MANIFEST
    if not path.exists():
        return {}

    data = json.loads(path.read_text())
    records: dict[str, MarkdownReportRecord] = {}
    for job_id, row in data.items():
        records[job_id] = MarkdownReportRecord(**row)
    return records


def save_manifest(report_dir: Path, records: dict[str, MarkdownReportRecord]) -> None:
    path = report_dir / MANIFEST
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")

    data = {job_id: dataclasses.asdict(record) for job_id, record in records.items()}
    try:
        with open(tmp, "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


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


def link_summary(summary: Path, entrypoint: Path) -> Path:
    """Create or replace a workspace-level Canary.md symlink."""
    target = os.path.relpath(entrypoint, summary.parent)
    if summary.is_symlink() or summary.is_file():
        summary.unlink()
    elif summary.exists():
        raise ValueError(f"{summary}: exists and is not a file or symlink")
    summary.symlink_to(target)
    return summary
