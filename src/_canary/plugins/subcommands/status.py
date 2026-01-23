# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import shutil
from typing import TYPE_CHECKING
from typing import Any

from rich.console import Console
from rich.table import Table

from ...hookspec import hookimpl
from ...status import Status as _Status
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
        parser.add_argument("--history", action="store_true", help="Print status history for specs")
        parser.add_argument(
            "specs", nargs=argparse.REMAINDER, help="Show status for these specific specs"
        )

    def execute(self, args: "argparse.Namespace") -> int:
        if args.history:
            self.print_spec_status_history(args.specs)
            return 0
        if args.specs:
            args.report_chars = "A"
        workspace = Workspace.load()
        results = workspace.db.get_results(ids=args.specs)
        table = self.get_status_table(results, args)
        console = Console()
        if table.row_count > shutil.get_terminal_size().lines:
            with console.pager():
                console.print(table, markup=True)
        else:
            console.print(table, markup=True)
        if args.durations:
            console.print(format_durations(results, args.durations))
        return 0

    def get_status_table(self, results: dict[str, Any], args: "argparse.Namespace") -> Table:
        rows = sorted(results.values(), key=sortkey)
        rows = filter_by_status(rows, args.report_chars)
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
        for row in rows:
            r: list[str] = []
            for col in cols:
                key = map[col]
                value = get_attribute(row, key)
                r.append(value)
            table.add_row(*r)
        return table

    def print_spec_status_history(self, ids: list[str]) -> None:
        workspace = Workspace.load()
        table = Table(expand=False)
        for col in ["Name", "ID", "Session", "Exit Code", "Duration", "Status", "Details"]:
            table.add_column(col)
        for id in ids:
            results = workspace.db.get_result_history(id)
            for entry in results:
                row: list[str] = []
                row.append(entry["spec_name"])
                row.append(entry["id"][:7])
                row.append(entry["session"])
                row.append(str(entry["status"].code))
                row.append(str(entry["timekeeper"].duration))
                row.append(str(entry["status"].display_name(style="rich")))
                row.append(str(entry["status"].reason))
                table.add_row(*row)
        console = Console()
        console.print(table, markup=True)


def sortkey(row: dict) -> tuple:
    c = 1
    if row["status"].category == "PASS":
        c = 0
    if row["status"].category == "FAIL":
        c = 2
    return (c, row["status"].status, row["timekeeper"].duration)


def get_attribute(row: dict[str, Any], attr: str) -> str:
    if attr == "id":
        return row["id"][:7]
    elif attr == "name":
        return row["spec_name"]  # fixme: add color
    elif attr == "fullname":
        return row["spec_fullname"]
    elif attr == "session":
        return row["session"]
    elif attr == "returncode":
        return str(row["status"].code)
    elif attr == "duration":
        return dformat(row["timekeeper"].duration)
    elif attr == "status_name":
        return row["status"].display_name(style="rich")
    elif attr == "status_reason":
        return row["status"].reason or ""
    raise AttributeError(attr)


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


def filter_by_status(rows: list[dict], chars: str | None) -> list[dict]:
    chars = chars or "dftns"
    if "A" in chars:
        return rows
    keep = [False] * len(rows)
    for i, row in enumerate(rows):
        status: _Status = row["status"]
        if "a" in chars:
            keep[i] = status.category != "PASS"
        elif status.category == "SKIP":
            keep[i] = "s" in chars
        elif status.category == "PASS":
            keep[i] = "p" in chars
        elif status.status in ("FAILED", "ERROR", "BROKEN"):
            keep[i] = "f" in chars
        elif status.status == "DIFFED":
            keep[i] = "d" in chars
        elif status.status == "TIMEOUT":
            keep[i] = "t" in chars
        elif status.state in ("READY", "PENDING"):
            keep[i] = "n" in chars
        elif status.category == "CANCEL":
            keep[i] = "n" in chars
        else:
            logger.warning(f"Unhandled status {status}")
    return [row for i, row in enumerate(rows) if keep[i]]


def format_durations(results: dict[str, Any], N: int) -> str:
    rows = sorted(results.values(), key=lambda x: x["timekeeper"].duration)
    ix = list(range(len(rows)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fp = io.StringIO()
    fp.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = rows[i]["timekeeper"].duration
        if duration < 0:
            continue
        name = rows[i]["spec_name"]
        id = rows[i]["id"][:7]
        fp.write("  %6.2f   %s %s\n" % (duration, id, name))
    return fp.getvalue().strip()


def dformat(arg: float) -> str:
    return "NA" if arg < 0 else f"{arg:.02f}"
