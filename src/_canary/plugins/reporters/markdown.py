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
from ..types import CanaryReporter

if TYPE_CHECKING:
    from ...session import Session


@hookimpl
def canary_session_reporter() -> CanaryReporter:
    return MarkdownReporter()


class MarkdownReporter(CanaryReporter):
    type = "markdown"
    description = "Markdown reporter"
    multipage = True

    def create(self, session: "Session | None" = None, **kwargs: Any) -> None:
        if session is None:
            raise ValueError("canary report markdown: session required")

        dest = string.Template(kwargs["dest"]).safe_substitute(canary_work_tree=session.work_tree)
        self.md_dir = os.path.join(dest, "MARKDOWN")
        self.index = os.path.join(dest, "canary-report.md")
        self.root = dest
        force_remove(self.md_dir)
        mkdirp(self.md_dir)
        for case in session.active_cases():
            file = os.path.join(self.md_dir, f"{case.id}.md")
            with open(file, "w") as fh:
                try:
                    self.generate_case_file(case, fh)
                except Exception as e:
                    ex = e if logging.DEBUG >= logging.get_level() else None
                    logging.warning(f"Issue writing report for test case ID:{case.id}", ex=ex)
        with open(self.index, "w") as fh:
            self.generate_index(session, fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logging.info(f"Markdown report written to {f}")

    def generate_case_file(self, case: TestCase, fh: TextIO) -> None:
        if case.masked():
            return
        fh.write(f"# {case.display_name}\n\n")
        self.render_test_info_table(case, fh)
        fh.write("## Test output\n")
        fh.write("\n```console\n")
        fh.write(case.output())
        fh.write("```\n\n")

    def render_test_info_table(self, case: TestCase, fh: TextIO) -> None:
        info: dict[str, str] = {
            "**Status**": case.status.name,
            "**Exit code**": str(case.returncode),
            "**ID**": str(case.id),
            "**Location**": case.working_directory,
            "**Duration**": f"{case.duration:.4f}",
        }
        fh.write("|||\n|---|---|\n")
        for key, val in info.items():
            fh.write(f"|{key.center(15, ' ')}| {val} |\n")
        fh.write("\n")

    def generate_index(self, session: "Session", fh: TextIO) -> None:
        fh.write("# Canary Summary\n\n")
        fh.write(
            "| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Invalid | Cancelled | Total |\n"
        )
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        totals: dict[str, list[TestCase]] = {}
        for case in session.active_cases():
            group = case.status.name.title()
            totals.setdefault(group, []).append(case)
        fh.write(f"| {config.system.host} ")
        fh.write(f"| {config.build.project} ")
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
        fh.write(f"| [{len(session.active_cases())}]({relpath}) |\n")
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)

    def generate_group_index(self, cases, fh: TextIO) -> None:
        key = cases[0].status.name
        fh.write(f"# {key} Summary\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")
        for case in sorted(cases, key=lambda c: c.name.lower()):
            file = os.path.join(self.md_dir, f"{case.id}.md")
            if not os.path.exists(file):
                raise ValueError(f"{file}: markdown file not found")
            link = f"[{case.display_name}](./{os.path.basename(file)})"
            duration = f"{case.duration:.2f}"
            status = case.status.name
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
                link = f"[{case.display_name}](./{os.path.basename(file)})"
                duration = f"{case.duration:.2f}"
                status = case.status.name
                fh.write(f"| {link} | {duration} | {status} |\n")
        fh.write("\n")
