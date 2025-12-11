# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import itertools
import re
import shutil
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from ... import status
from ...hookspec import hookimpl
from ...testcase import TestCase
from ...third_party.color import colorize
from ...util import glyphs
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Status())


class Status(CanarySubcommand):
    name = "status"
    description = "Print information about a test run"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument(
            "--durations",
            nargs="?",
            type=int,
            const=10,
            metavar="N",
            help="Show N slowest test durations (N<0 for all) [default: 10]",
        )
        parser.add_argument(
            "-o",
            dest="format_cols",
            default="ID,Name,Session,Exit Code,Duration,Status,Details",
            action=StatusFormatAction,
            help="Comma separated list of fields to print to the screen [default: %(default)s]. "
            "Choices are:\n\n"
            "• Name: the testcase name\n\n"
            "• FullName: the testcase full name (name including relative execution path)\n\n"
            "• Session: the session name the testcase was last ran in\n\n"
            "• Exit Code: the testcase's exit code\n\n"
            "• Duration: testcase duration\n\n"
            "• Status: testcase exit status\n\n"
            "• Details: additional details, if any\n\n",
        )
        parser.add_argument(
            "-r",
            dest="report_chars",
            action=ReportCharAction,
            default="dftns",
            metavar="char",
            help="Show test summary info as specified by chars: "
            "(p)assed, "
            "(t)imeout "
            "(d)iffed, "
            "(f)ailed, "
            "(n)ot run, "
            "(s)kipped, "
            "(a)ll (except passed), "
            "(A)ll.  [default: dftns]",
        )
        parser.add_argument(
            "--sort-by",
            default="name",
            choices=("duration", "name"),
            help="Sort cases by this field [default: %(default)s]",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        cases = workspace.load_testcases()
        table = self.get_status_table(cases, args)
        console = Console()
        if table.row_count > shutil.get_terminal_size().lines:
            with console.pager():
                console.print(table, markup=True)
        else:
            console.print(table, markup=True)
        if args.durations:
            console.print(format_durations(cases, args.durations))
        return 0

    def get_status_table(self, cases: list[TestCase], args: "argparse.Namespace") -> Table:
        cases.sort(key=lambda c: (c.status.category, c.status.status, c.timekeeper.duration))
        cases = filter_by_status(cases, args.report_chars)
        cols = args.format_cols.split(",")
        table = Table(expand=True)
        for col in cols:
            table.add_column(col)

        map: dict[str, str] = {
            "ID": "id",
            "Name": "name",
            "FullName": "fullname",
            "Session": "session",
            "Exit Code": "returncode",
            "Duration": "duration",
            "Status": "status_name",
            "Details": "status_reason",
        }
        for case in cases:
            row: list[str] = []
            for col in cols:
                key = map[col]
                value = get_case_attribute(case, key)
                row.append(value)
            table.add_row(*row)
        return table


def get_case_attribute(case: TestCase, attr: str) -> str:
    if attr == "id":
        return case.id[:7]
    elif attr == "name":
        return case.display_name(style="rich")
    elif attr == "fullname":
        return case.display_name(style="rich", full=True)
    elif attr == "session":
        return str(case.workspace.session)
    elif attr == "returncode":
        return str(case.status.code)
    elif attr == "duration":
        return dformat(case.timekeeper.duration)
    elif attr == "status_name":
        return case.status.display_name(style="rich")
    elif attr == "status_reason":
        return case.status.reason or ""
    raise AttributeError(attr)


def pretty_test_name(name: str) -> str:
    colors = itertools.cycle("bmgycr")
    if match := re.search(r"(\w+)\[(.*)\]", name):
        stem = match.group(1)
        params = match.group(2).split(",")
        string = ",".join("@%s{%s}" % (next(colors), p) for p in params)
        return colorize("%s[%s]" % (stem, string))
    return name


def pretty_status_name(name: str) -> str:
    color: str = ""
    fmt: str = "%(name)s"
    if name in ("RETRY", "PENDING", "READY", "SKIPPED", "BLOCKED"):
        color = status.Status.categories[name][1][0]
        fmt = "@*c{NOT RUN} (@*%(color)s{%(name)s})"
    elif name in ("DIFFED", "FAILED", "BROKEN", "ERROR", "TIMEOUT"):
        color = status.Status.categories[name][1][0]
        fmt = "@*r{FAILED} (@*%(color)s{%(name)s})"
    else:
        color = status.Status.categories[name][1][0]
        fmt = "@*%(color)s{%(name)s}"
    return colorize(fmt % {"color": color, "name": name})


class ReportCharAction(argparse.Action):
    chars = "pftdfnsxaA"

    def __call__(self, parser, args, values, option_string=None):
        for value in values:
            if value not in self.chars:
                parser.error(f"Invalid report char {value!r}, choose any from {self.chars!r}")
        setattr(args, self.dest, values)


class StatusFormatAction(argparse.Action):
    _choices: list[str] = [
        "ID",
        "FullName",
        "Name",
        "Session",
        "Exit Code",
        "Duration",
        "Status",
        "Details",
    ]

    def __call__(self, parser, namespace, value, option_string=None):
        items = value.split(",")
        for i, item in enumerate(items):
            if choice := match_case_insensitive(item, self._choices):
                items[i] = choice
            else:
                choices = ",".join(self._choices)
                parser.error(f"Invalid status format {item!r}, choose from {choices}")
        value = ",".join(items)
        setattr(namespace, self.dest, value)


def match_case_insensitive(s: str, choices: list[str]) -> str | None:
    for choice in choices:
        if s.lower() == choice.lower():
            return choice
    return None


def filter_by_status(cases: list[TestCase], chars: str | None) -> list[TestCase]:
    chars = chars or "dftns"
    if "A" in chars:
        return cases
    keep = [False] * len(cases)
    for i, case in enumerate(cases):
        if "a" in chars:
            keep[i] = case.status.category != "PASS"
        elif case.status.category == "SKIP":
            keep[i] = "s" in chars
        elif case.status.category == "PASS":
            keep[i] = "p" in chars
        elif case.status.status in ("FAILED", "ERROR", "BROKEN"):
            keep[i] = "f" in chars
        elif case.status.status == "DIFFED":
            keep[i] = "d" in chars
        elif case.status.status == "TIMEOUT":
            keep[i] = "t" in chars
        elif case.status.state in ("READY", "PENDING"):
            keep[i] = "n" in chars
        elif case.status.category == "CANCEL":
            keep[i] = "n" in chars
        else:
            logger.warning(f"Unhandled status {case.status}")
    return [case for i, case in enumerate(cases) if keep[i]]


def format_durations(cases: list[TestCase], N: int) -> str:
    cases.sort(key=lambda x: x.timekeeper.duration)
    ix = list(range(len(cases)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fp = io.StringIO()
    fp.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = cases[i].timekeeper.duration
        if duration < 0:
            continue
        name = cases[i].display_name(style="rich")
        id = cases[i].id[:7]
        fp.write("  %6.2f   %s %s\n" % (duration, id, name))
    return fp.getvalue().strip()


def dformat(arg: float) -> str:
    return "NA" if arg < 0 else f"{arg:.02f}"
