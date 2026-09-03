# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary status`` subcommand for displaying test run results."""

import argparse
import io
import json
import shutil
import sys
from typing import TYPE_CHECKING
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from ..hookspec import hookimpl
from ..job import JobState
from ..status import Status as _Status
from ..util import glyphs
from ..util import logging
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Status())


class Status(CanarySubcommand):
    """Print a tabular or JSON summary of test results from the current workspace."""

    name = "status"
    description = "Print information about a test run"

    def setup_parser(self, parser: "Parser"):
        """Register ``--durations``, ``-o`` columns, ``-r`` report chars, ``--sort-by``, ``--json``, and ``--full-ids``."""
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
            "• ID: the job ID (7-char prefix by default; use --full-ids for full 64-char ID)\n\n"
            "• Name: the job name\n\n"
            "• FullName: the job full name (name including relative execution path)\n\n"
            "• FilePath: path to the test file relative to file_root\n\n"
            "• Session: the session name the job was last ran in\n\n"
            "• Exit Code: the job's exit code\n\n"
            "• Duration: job duration\n\n"
            "• Status: job exit status\n\n"
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
            "--json",
            dest="output_json",
            action="store_true",
            default=False,
            help="Emit results as a JSON array instead of a terminal table",
        )
        parser.add_argument(
            "--full-ids",
            dest="full_ids",
            action="store_true",
            default=False,
            help="Show full 64-character spec IDs instead of 7-character prefixes",
        )
        parser.add_argument(
            "specs", nargs=argparse.REMAINDER, help="Show status history for these specific specs"
        )

    def execute(self, args: "argparse.Namespace") -> int:
        """Load workspace results and print the status table or JSON output, returning 0."""
        if args.specs:
            self.print_spec_status_history(args.specs, args)
            return 0
        workspace = Workspace.load()
        results = workspace.db.get_results()

        if getattr(args, "output_json", False):
            self.print_json(results, args)
            return 0

        table = self.get_status_table(results, args)
        console = Console()
        use_pager = sys.stdout.isatty() and table.row_count > shutil.get_terminal_size().lines
        if use_pager:
            with console.pager():
                console.print(table)
        else:
            console.print(table)
        if args.durations:
            console.print(format_durations(results, args.durations))
        return 0

    def print_json(self, results: dict[str, Any], args: "argparse.Namespace") -> None:
        """Emit all matching results as a JSON array."""
        rows = sorted(results.values(), key=sortkey)
        rows = filter_by_status(rows, args.report_chars)

        out = []
        for row in rows:
            tk = row["timekeeper"]
            submitted = (
                tk.get("_submitted", -1) if isinstance(tk, dict) else getattr(tk, "_submitted", -1)
            )
            staged = tk.get("_staged", -1) if isinstance(tk, dict) else getattr(tk, "_staged", -1)
            started = (
                tk.get("_started", -1) if isinstance(tk, dict) else getattr(tk, "_started", -1)
            )
            stopped = (
                tk.get("_stopped", -1) if isinstance(tk, dict) else getattr(tk, "_stopped", -1)
            )
            finished = (
                tk.get("_finished", -1) if isinstance(tk, dict) else getattr(tk, "_finished", -1)
            )

            def elapsed(a: float, b: float) -> float:
                return round(b - a, 6) if a > 0 and b > 0 else -1.0

            sid = row["id"] if getattr(args, "full_ids", False) else row["id"][:7]
            status: _Status = row["status"]
            out.append(
                {
                    "id": sid,
                    "name": row["spec_name"],
                    "fullname": row["spec_fullname"],
                    "file_path": row.get("file_path", ""),
                    "session": row["session"],
                    "exit_code": status.code,
                    "status": {
                        "category": status.category.value,
                        "outcome": status.outcome.name,
                        "reason": status.reason,
                    },
                    "timings": {
                        "pending": elapsed(submitted, staged),
                        "setup": elapsed(staged, started),
                        "running": elapsed(started, stopped),
                        "teardown": elapsed(stopped, finished),
                        "total": elapsed(submitted, finished),
                    },
                }
            )

        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")

    def get_status_table(self, results: dict[str, Any], args: "argparse.Namespace") -> Table:
        """Build a Rich ``Table`` of test results filtered and sorted per *args*."""
        rows = sorted(results.values(), key=sortkey)
        rows = filter_by_status(rows, args.report_chars)
        cols = args.format_cols.split(",")

        table = Table(expand=True, box=box.SQUARE)
        for col in cols:
            table.add_column(col)

        col_map: dict[str, str] = {
            "ID": "id",
            "Name": "name",
            "FullName": "fullname",
            "FilePath": "file_path",
            "Session": "session",
            "Exit Code": "returncode",
            "Duration": "duration",
            "Status": "status_name",
            "Details": "status_reason",
        }
        for row in rows:
            r: list[str] = []
            for col in cols:
                key = col_map[col]
                value = get_attribute(row, key, full_ids=getattr(args, "full_ids", False))
                r.append(value)
            table.add_row(*r)
        return table

    def print_spec_status_history(self, ids: list[str], args: "argparse.Namespace") -> None:
        """Print the full history of results across sessions for each spec ID in *ids*."""
        workspace = Workspace.load()
        table = Table(expand=False, box=box.SQUARE)
        for col in ["Name", "ID", "Session", "Exit Code", "Duration", "Status", "Details"]:
            table.add_column(col)
        for id in ids:
            results = workspace.db.get_result_history(id)
            for entry in results:
                row: list[str] = []
                row.append(entry["spec_name"])
                sid = entry["id"] if args.full_ids else entry["id"][:7]
                row.append(sid)
                row.append(entry["session"])
                row.append(str(entry["status"].code))
                row.append(str(entry["timekeeper"].duration()))
                row.append(str(entry["status"].display_name(style="rich")))
                row.append(str(entry["status"].reason))
                table.add_row(*row)
        console = Console()
        console.print(table)


def sortkey(row: dict) -> tuple:
    """Return a sort tuple for a result row: ``(category_rank, outcome, duration)``."""
    c = 1
    if row["status"].is_success():
        c = 0
    if row["status"].is_failure():
        c = 2
    return (c, row["status"].outcome, row["timekeeper"].duration())


def get_attribute(row: dict[str, Any], attr: str, *, full_ids: bool = False) -> str:
    """Extract a display string for column *attr* from a result *row*.

    Args:
        row: A workspace result dict containing job metadata.
        attr: The column key (e.g. ``"id"``, ``"name"``, ``"duration"``).
        full_ids: When ``True``, return the full 64-character ID rather than a 7-char prefix.

    Returns:
        A formatted string suitable for display in a status table cell.

    Raises:
        AttributeError: If *attr* is not a recognised column key.
    """
    if attr == "id":
        return row["id"] if full_ids else row["id"][:7]
    elif attr == "name":
        return row["spec_name"]
    elif attr == "fullname":
        return row["spec_fullname"]
    elif attr == "file_path":
        return row.get("file_path", "")
    elif attr == "session":
        return row["session"]
    elif attr == "returncode":
        return str(row["status"].code)
    elif attr == "duration":
        return dformat(row["timekeeper"].duration())
    elif attr == "status_name":
        return row["status"].display_name(style="rich")
    elif attr == "status_reason":
        return row["status"].reason or ""
    raise AttributeError(attr)


class ReportCharAction(argparse.Action):
    """Validate and store the ``-r`` report-character filter string."""

    chars = "pftdfnsxaA"

    def __call__(self, parser, args, values, option_string=None):
        for value in values:
            if value not in self.chars:
                parser.error(f"Invalid report char {value!r}, choose any from {self.chars!r}")
        setattr(args, self.dest, values)


class StatusFormatAction(argparse.Action):
    """Validate and normalise the ``-o`` comma-separated column list (case-insensitive)."""

    _choices: list[str] = [
        "ID",
        "FullName",
        "Name",
        "FilePath",
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
    """Return the matching choice for *s* (case-insensitive), or ``None`` if not found."""
    for choice in choices:
        if s.lower() == choice.lower():
            return choice
    return None


def filter_by_status(rows: list[dict], chars: str | None) -> list[dict]:
    """Return the subset of *rows* whose status matches the report-character filter *chars*."""
    from ..status import Outcome

    chars = chars or "dftns"
    if "A" in chars:
        return rows
    keep = [False] * len(rows)
    for i, row in enumerate(rows):
        status: _Status = row["status"]
        state: JobState = row["state"]
        if "a" in chars:
            keep[i] = not status.is_success()
        elif status.is_skipped():
            keep[i] = "s" in chars
        elif status.is_success():
            keep[i] = "p" in chars
        elif status.outcome in (Outcome.FAILED, Outcome.ERROR, Outcome.BROKEN):
            keep[i] = "f" in chars
        elif status.is_diffed():
            keep[i] = "d" in chars
        elif status.is_timeout():
            keep[i] = "t" in chars
        elif not state.is_done():
            keep[i] = "n" in chars
        elif status.is_cancelled():
            keep[i] = "n" in chars
        else:
            logger.warning(f"Unhandled status {status}")
    return [row for i, row in enumerate(rows) if keep[i]]


def format_durations(results: dict[str, Any], N: int) -> str:
    """Return a formatted string listing the *N* slowest test durations."""
    rows = sorted(results.values(), key=lambda x: x["timekeeper"].duration())
    ix = list(range(len(rows)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fp = io.StringIO()
    fp.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = rows[i]["timekeeper"].duration()
        if duration < 0:
            continue
        name = rows[i]["spec_name"]
        id = rows[i]["id"][:7]
        fp.write("  %6.2f   %s %s\n" % (duration, id, name))
    return fp.getvalue().strip()


def dformat(arg: float) -> str:
    """Format a duration *arg* as ``"%.2f"`` or ``"NA"`` if negative."""
    return "NA" if arg < 0 else f"{arg:.02f}"
