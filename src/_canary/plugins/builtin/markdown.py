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
    from ...testcase import TestCase

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
        cases = workspace.load_testcases()
        work_tree = workspace.view or workspace.sessions_dir
        dest = string.Template(kwargs["dest"]).safe_substitute(canary_work_tree=str(work_tree))
        self.md_dir = os.path.join(dest, self.default_output)
        self.index = os.path.join(dest, "canary-report.md")
        self.root = dest
        force_remove(self.md_dir)
        mkdirp(self.md_dir)
        for case in cases:
            file = os.path.join(self.md_dir, f"{case.id}.md")
            with open(file, "w") as fh:
                try:
                    self.generate_case_file(case, fh)
                except Exception as e:
                    logger.exception(f"Issue writing report for test case ID:{case.id}")
        with open(self.index, "w") as fh:
            self.generate_index(cases, fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logger.info(f"Markdown report written to {f}")

    def generate_case_file(self, case: "TestCase", fh: TextIO) -> None:
        fh.write(f"# {case.display_name()}\n\n")
        self.render_test_info_table(case, fh)
        fh.write("## Test output\n")
        fh.write("\n```console\n")
        fh.write(case.read_output())
        fh.write("```\n\n")

    def render_test_info_table(self, case: "TestCase", fh: TextIO) -> None:
        info: dict[str, str] = {
            "**Status**": case.status.category,
            "**Exit code**": str(case.status.code),
            "**ID**": str(case.id),
            "**Location**": str(case.workspace.dir),
            "**Duration**": f"{case.timekeeper.duration:.4f}",
        }
        fh.write("|||\n|---|---|\n")
        for key, val in info.items():
            fh.write(f"|{key.center(15, ' ')}| {val} |\n")
        fh.write("\n")

    def generate_index(self, cases: list["TestCase"], fh: TextIO) -> None:
        fh.write("# Canary Summary\n\n")
        fh.write(
            "| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Invalid | Cancelled | Total |\n"
        )
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        totals: dict[str, list["TestCase"]] = {}
        for case in cases:
            group = case.status.category.title()
            totals.setdefault(group, []).append(case)
        fh.write(f"| {os.uname().nodename} ")
        fh.write(f"| {config.get('build:project')} ")
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
        fh.write(f"| [{len(cases)}]({relpath}) |\n")
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)

    def generate_group_index(self, cases, fh: TextIO) -> None:
        key = cases[0].status.category
        fh.write(f"# {key} Summary\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")
        for case in sorted(cases, key=lambda c: c.name.lower()):
            file = os.path.join(self.md_dir, f"{case.id}.md")
            if not os.path.exists(file):
                raise ValueError(f"{file}: markdown file not found")
            link = f"[{case.display_name()}](./{os.path.basename(file)})"
            duration = f"{case.timekeeper.duration:.2f}"
            status = case.status.category
            fh.write(f"| {link} | {case.id} | {duration} | {status} |\n")

    def generate_all_tests_index(self, totals: dict, fh: TextIO) -> None:
        fh.write("# Test Results\n")
        fh.write("| Test | Duration | Status |\n")
        fh.write("| --- | --- | --- |\n")
        for group, cases in totals.items():
            for case in sorted(cases, key=lambda c: c.duration):
                file = os.path.join(self.md_dir, f"{case.id}.md")
                if not os.path.exists(file):
                    raise ValueError(f"{file}: markdown file not found")
                link = f"[{case.display_name()}](./{os.path.basename(file)})"
                duration = f"{case.timekeeper.duration:.2f}"
                status = case.status.category
                fh.write(f"| {link} | {duration} | {status} |\n")
        fh.write("\n")
