import os
import string
from typing import TextIO

from _nvtest import config
from _nvtest.reporter import Reporter
from _nvtest.test.case import TestCase
from _nvtest.util import logging
from _nvtest.util.filesystem import force_remove
from _nvtest.util.filesystem import mkdirp


class MarkdownReporter(Reporter):
    def create(self, dest: str = "$nvtest_work_tree") -> None:  # type: ignore
        """Create a multi-page markdown report

        Args:
          dest: Directory to write report

        """
        dest = string.Template(dest).safe_substitute(nvtest_work_tree=self.session.work_tree)
        self.md_dir = os.path.join(dest, "MARKDOWN")
        self.index = os.path.join(dest, "Results.md")
        self.root = dest
        force_remove(self.md_dir)
        mkdirp(self.md_dir)
        for case in self.data.cases:
            file = os.path.join(self.md_dir, f"{case.id}.md")
            with open(file, "w") as fh:
                self.generate_case_file(case, fh)
        with open(self.index, "w") as fh:
            self.generate_index(fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logging.info(f"Markdown report written to {f}")

    def generate_case_file(self, case: TestCase, fh: TextIO) -> None:
        if case.status.value in ("skipped", "masked"):
            return
        fh.write(f"**Test:** {case.display_name}\n")
        fh.write(f"**Status:** {case.status.name}\n")
        fh.write(f"**Exit code:** {case.returncode}\n")
        fh.write(f"**ID:** {case.id}\n")
        fh.write(f"**Duration:** {case.duration:.4f}\n\n")
        fh.write("## Test output\n")
        fh.write("\n```console\n")
        if os.path.exists(case.logfile()):
            with open(case.logfile()) as fp:
                fh.write(fp.read())
        else:
            fh.write("Log file does not exist\n")
        fh.write("```\n")

    def generate_index(self, fh: TextIO) -> None:
        fh.write("# NVTest Summary\n\n")
        fh.write("| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Total |\n")
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        totals: dict[str, list[TestCase]] = {}
        for case in self.data.cases:
            if case.status == "masked":
                continue
            group = case.status.name.title()
            totals.setdefault(group, []).append(case)
        fh.write(f"| {config.system.host} ")
        fh.write(f"| {config.build.project} ")
        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass"):
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
        fh.write(f"| [{len(self.data.cases)}]({relpath}) |\n")
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)

    def generate_group_index(self, cases, fh: TextIO) -> None:
        assert all([cases[0].status.name == c.status.name for c in cases[1:]])
        fh.write(f"# {cases[0].status.name} Summary\n\n")
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
