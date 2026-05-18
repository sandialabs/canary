# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import string
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
    return MarkdownReporter()


class MarkdownReporter(CanaryReporter):
    type = "markdown"
    description = "Markdown reporter"
    multipage = True
    default_output = "MARKDOWN"

    def create(self, **kwargs: Any) -> None:
        workspace = Workspace.load()
        jobs = workspace.load_jobs()
        work_tree = workspace.view or workspace.sessions_dir
        dest = string.Template(kwargs["dest"]).safe_substitute(canary_work_tree=str(work_tree))
        self.md_dir = os.path.join(dest, self.default_output)
        self.index = os.path.join(dest, "canary-report.md")
        self.root = dest
        force_remove(self.md_dir)
        mkdirp(self.md_dir)
        for job in jobs:
            file = os.path.join(self.md_dir, f"{job.id}.md")
            with open(file, "w") as fh:
                try:
                    self.generate_case_file(job, fh)
                except Exception as e:
                    logger.exception(f"Issue writing report for test job ID:{job.id}")
        with open(self.index, "w") as fh:
            self.generate_index(jobs, fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logger.info(f"Markdown report written to {f}")

    def generate_case_file(self, job: "Job", fh: TextIO) -> None:
        fh.write(f"# {job.display_name()}\n\n")
        self.render_test_info_table(job, fh)
        fh.write("## Test output\n")
        fh.write("\n```console\n")
        fh.write(job.read_output())
        fh.write("```\n\n")

    def render_test_info_table(self, job: "Job", fh: TextIO) -> None:
        info: dict[str, str] = {
            "**Status**": job.status.outcome.name,
            "**Exit code**": str(job.status.code),
            "**ID**": str(job.id),
            "**Location**": str(job.workspace.dir),
            "**Duration**": f"{job.timekeeper.duration():.4f}",
        }
        fh.write("|||\n|---|---|\n")
        for key, val in info.items():
            fh.write(f"|{key.center(15, ' ')}| {val} |\n")
        fh.write("\n")

    def generate_index(self, jobs: list["Job"], fh: TextIO) -> None:
        fh.write("# Canary Summary\n\n")
        fh.write(
            "| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Invalid | Cancelled | Total |\n"
        )
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        totals: dict[str, list["Job"]] = {}
        for job in jobs:
            group = job.status.outcome.name.title()
            totals.setdefault(group, []).append(job)
        fh.write(f"| {os.uname().nodename} ")
        fh.write(f"| {config.get('cmake:project')} ")
        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Invalid", "Cancelled"):
            if group not in totals:
                fh.write("| 0 ")
            else:
                n = len(totals[group])
                file = os.path.join(self.md_dir, "%s.md" % "".join(group.split()))
                relpath = os.path.relpath(file, self.root)
                fh.write(f"| [{n}]({relpath}) ")
                with open(file, "w") as fp:
                    self.generate_group_index(totals[group], fp)
        file = os.path.join(self.md_dir, "Total.md")
        relpath = os.path.relpath(file, self.root)
        fh.write(f"| [{len(jobs)}]({relpath}) |\n")
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)

    def generate_group_index(self, jobs, fh: TextIO) -> None:
        key = jobs[0].status.outcome
        fh.write(f"# {key} Summary\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")
        for job in sorted(jobs, key=lambda c: c.name.lower()):
            file = os.path.join(self.md_dir, f"{job.id}.md")
            if not os.path.exists(file):
                raise ValueError(f"{file}: markdown file not found")
            link = f"[{job.display_name()}](./{os.path.basename(file)})"
            duration = f"{job.timekeeper.duration():.2f}"
            outcome = job.status.outcome
            fh.write(f"| {link} | {job.id} | {duration} | {outcome} |\n")

    def generate_all_tests_index(self, totals: dict, fh: TextIO) -> None:
        fh.write("# Test Results\n")
        fh.write("| Test | Duration | Status |\n")
        fh.write("| --- | --- | --- |\n")
        for group, jobs in totals.items():
            for job in sorted(jobs, key=lambda c: c.timekeeper.duration()):
                file = os.path.join(self.md_dir, f"{job.id}.md")
                if not os.path.exists(file):
                    raise ValueError(f"{file}: markdown file not found")
                link = f"[{job.display_name()}](./{os.path.basename(file)})"
                duration = f"{job.timekeeper.duration():.2f}"
                outcome = job.status.outcome
                fh.write(f"| {link} | {duration} | {outcome} |\n")
        fh.write("\n")
