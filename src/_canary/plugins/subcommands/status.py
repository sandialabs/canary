# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import itertools
import re
from typing import TYPE_CHECKING

from ... import status
from ...hookspec import hookimpl
from ...testcase import TestCase
from ...third_party import colify
from ...third_party.color import clen
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
        parser.add_argument(
            "--dump", action="store_true", help="Dump test cases to lock lock file [default: False]"
        )
        parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        cases = workspace.load_testcases()
        table = self.get_status_table(cases, args)
        fh = io.StringIO()
        colify.colify_table(table, output=fh)
        print(fh.getvalue().strip())
        if args.durations:
            print_durations(cases, N=args.durations)
        return 0

    def get_status_table(
        self, cases: list[TestCase], args: "argparse.Namespace"
    ) -> list[list[str]]:
        cases.sort(key=lambda c: status_sort_map.get(c.status.name, 50))
        cases = filter_by_status(cases, args.report_chars)
        cols = args.format_cols.split(",")
        map: dict[str, str] = {
            "ID": "id",
            "Name": "name",
            "FullName": "fullname",
            "Session": "session",
            "Exit Code": "returncode",
            "Duration": "duration",
            "Status": "status_name",
            "Details": "status_message",
        }
        table: list[list[str]] = []
        widths = [len(_) for _ in cols]
        for case in cases:
            row: list[str] = []
            for j, name in enumerate(cols):
                key = map[name]
                value = get_case_attribute(case, key)
                widths[j] = max(widths[j], clen(value))
                row.append(value)
            table.append(row)
        hlines: list[str] = ["=" * width for width in widths]
        table.insert(0, cols)
        table.insert(1, hlines)
        return table


def get_case_attribute(case: TestCase, attr: str) -> str:
    if attr == "id":
        return colorize("@*b{%s}" % case.id[:7])
    elif attr == "name":
        return pretty_test_name(case.spec.display_name)
    elif attr == "fullname":
        return pretty_test_name(str(case.spec.file_path.parent / case.spec.display_name))
    elif attr == "session":
        return str(case.workspace.session)
    elif attr == "returncode":
        return str(case.status.code)
    elif attr == "duration":
        return colorize("@*{%s}" % dformat(case.timekeeper.duration))
    elif attr == "status_name":
        return pretty_status_name(case.status.name)
    elif attr == "status_message":
        return case.status.message or ""
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
    if name in ("RETRY", "PENDING", "READY", "SKIPPED"):
        color = status.Status.defaults[name][1][0]
        fmt = "@*c{NOT RUN} (@*%(color)s{%(name)s})"
    elif name == "NOT_RUN":
        color = status.Status.defaults[name][1][0]
        fmt = "@*%(color)s{NOT RUN}"
    elif name in ("DIFFED", "FAILED", "TIMEOUT", "INVALID", "UNKNOWN"):
        color = status.Status.defaults[name][1][0]
        fmt = "@*r{FAILED} (@*%(color)s{%(name)s})"
    else:
        color = status.Status.defaults[name][1][0]
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


status_sort_map = {
    "CREATED": 0,
    "RETRY": 0,
    "PENDING": 0,
    "READY": 0,
    "RUNNING": 0,
    "SUCCESS": 10,
    "XFAIL": 11,
    "XDIFF": 12,
    "CANCELLED": 20,
    "SKIPPED": 21,
    "NOT_RUN": 22,
    "TIMEOUT": 23,
    "DIFFED": 30,
    "FAILED": 31,
    "ERROR": 32,
    "UNKNOWN": 40,
}


def filter_by_status(cases: list[TestCase], chars: str | None) -> list[TestCase]:
    chars = chars or "dftns"
    if "A" in chars:
        return cases
    keep = [False] * len(cases)
    for i, case in enumerate(cases):
        stat = case.status.name
        if "a" in chars:
            keep[i] = stat != "SUCCESS"
        elif stat == "SKIPPED":
            keep[i] = "s" in chars
        elif stat in ("SUCCESS", "XDIFF", "XFAIL"):
            keep[i] = "p" in chars
        elif stat in ("FAILED", "ERROR"):
            keep[i] = "f" in chars
        elif stat == "DIFFED":
            keep[i] = "d" in chars
        elif stat == "TIMEOUT":
            keep[i] = "t" in chars
        elif stat == "INVALId":
            keep[i] = "n" in chars
        elif stat in ("READY", "CREATED", "PENDING", "CANCELLED", "NOT_RUN"):
            keep[i] = "n" in chars
        else:
            logger.warning(f"Unhandled status {stat}")
    return [case for i, case in enumerate(cases) if keep[i]]


def print_durations(cases: list[TestCase], N: int) -> None:
    cases.sort(key=lambda x: x.timekeeper.duration)
    fh = io.StringIO()
    ix = list(range(len(cases)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fh.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = cases[i].timekeeper.duration
        if duration < 0:
            continue
        name = cases[i].display_name()
        id = cases[i].id
        fh.write("  %6.2f   %s %s\n" % (duration, id, name))
    fh.write("\n")
    print(fh.getvalue().strip())


def dformat(arg: float) -> str:
    return "NA" if arg < 0 else f"{arg:.02f}"
