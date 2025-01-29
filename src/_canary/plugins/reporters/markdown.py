import argparse
import os
import string
from typing import TextIO

from ... import config
from ...config.argparsing import Parser
from ...test.case import TestCase
from ...util import logging
from ...util.filesystem import force_remove
from ...util.filesystem import mkdirp
from ..hookspec import hookimpl
from ..types import CanaryReporterSubcommand
from .common import load_session


@hookimpl
def canary_reporter_subcommand() -> CanaryReporterSubcommand:
    return CanaryReporterSubcommand(
        name="markdown",
        description="Markdown reporter",
        setup_parser=setup_parser,
        execute=markdown,
    )


def setup_parser(parser: Parser) -> None:
    sp = parser.add_subparsers(dest="subcommand", metavar="subcommands")
    p = sp.add_parser("create", help="Create multi-file Markdown report")
    p.add_argument("--dest", help="Output directory", default="$canary_work_tree")


def markdown(args: argparse.Namespace) -> None:
    if args.subcommand == "create":
        reporter = MarkdownReporter()
        reporter.create(dest=args.dest)
    else:
        raise ValueError(f"{args.subcommand}: unknown Markdown report subcommand")


class MarkdownReporter:
    def __init__(self):
        self.session = load_session()

    def create(self, dest: str) -> None:
        dest = string.Template(dest).safe_substitute(canary_work_tree=self.session.work_tree)
        self.md_dir = os.path.join(dest, "MARKDOWN")
        self.index = os.path.join(dest, "Results.md")
        self.root = dest
        force_remove(self.md_dir)
        mkdirp(self.md_dir)
        for case in self.session.active_cases():
            file = os.path.join(self.md_dir, f"{case.id}.md")
            with open(file, "w") as fh:
                self.generate_case_file(case, fh)
        with open(self.index, "w") as fh:
            self.generate_index(fh)
        f = os.path.relpath(self.index, config.invocation_dir)
        logging.info(f"Markdown report written to {f}")

    def generate_case_file(self, case: TestCase, fh: TextIO) -> None:
        if case.masked():
            return
        fh.write(f"**Test:** {case.display_name}\n")
        if case.defective():
            fh.write("**Status:** Defective\n")
        else:
            fh.write(f"**Status:** {case.status.name}\n")
        fh.write(f"**Exit code:** {case.returncode}\n")
        fh.write(f"**ID:** {case.id}\n")
        fh.write(f"**Duration:** {case.duration:.4f}\n\n")
        fh.write("## Test output\n")
        fh.write("\n```console\n")
        if case.defective():
            fh.write(f"{case.defect}\n")
        elif os.path.exists(case.logfile()):
            with open(case.logfile()) as fp:
                fh.write(fp.read().strip() + "\n")
        else:
            fh.write("Log file does not exist\n")
        fh.write("```\n")

    def generate_index(self, fh: TextIO) -> None:
        fh.write("# Canary Summary\n\n")
        fh.write(
            "| Site | Project | Not Run | Timeout | Fail | Diff | Pass | Defective | Cancelled | Total |\n"
        )
        fh.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        totals: dict[str, list[TestCase]] = {}
        for case in self.session.active_cases():
            group = "Defective" if case.defective() else case.status.name.title()
            totals.setdefault(group, []).append(case)
        fh.write(f"| {config.system.host} ")
        fh.write(f"| {config.build.project} ")
        for group in ("Not Run", "Timeout", "Fail", "Diff", "Pass", "Defective", "Cancelled"):
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
        fh.write(f"| [{len(self.session.active_cases())}]({relpath}) |\n")
        with open(file, "w") as fp:
            self.generate_all_tests_index(totals, fp)

    def generate_group_index(self, cases, fh: TextIO) -> None:
        key = "Defective" if cases[0].defective() else cases[0].status.name
        fh.write(f"# {key} Summary\n\n")
        fh.write("| Test | ID | Duration | Status |\n")
        fh.write("| --- | --- | --- | --- |\n")
        for case in sorted(cases, key=lambda c: c.name.lower()):
            file = os.path.join(self.md_dir, f"{case.id}.md")
            if not os.path.exists(file):
                raise ValueError(f"{file}: markdown file not found")
            link = f"[{case.display_name}](./{os.path.basename(file)})"
            duration = f"{case.duration:.2f}"
            status = "Defective" if case.defective() else case.status.name
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
                status = "Defective" if case.defective() else case.status.name
                fh.write(f"| {link} | {duration} | {status} |\n")
        fh.write("\n")
