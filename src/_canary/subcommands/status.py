# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary status`` subcommand for displaying test run results."""

import argparse
import io
import json
import sys
from typing import TYPE_CHECKING
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from .. import app
from ..core.job import JobState
from ..core.status import Status as _Status
from ..plugins.hookspec import hookimpl
from ..util import glyphs
from ..util import logging
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser

logger = logging.get_logger(__name__)

# Number of jobs below which the full table is always shown (unless --failed).
_AUTO_EXPAND_THRESHOLD = 20

# Default columns for the concise auto-expand view (small runs, ≤ threshold).
_DEFAULT_COLS_CONCISE = "ID,Name,Status,Duration,Details"
# Default columns for the full explicit table (--all or --failed).
_DEFAULT_COLS_FULL = "ID,Name,Session,Exit Code,Duration,Status,Details"


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
            default=None,
            action=StatusFormatAction,
            help="Comma separated list of fields to print to the screen "
            f"[default for small runs: {_DEFAULT_COLS_CONCISE}; "
            f"default for large runs / --all / --failed: {_DEFAULT_COLS_FULL}]. "
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
            default="dftnrs",
            metavar="char",
            help="Show test summary info as specified by chars: "
            "(p)assed, "
            "(t)imeout "
            "(d)iffed, "
            "(f)ailed, "
            "(r)unning, "
            "(n)ot run, "
            "(s)kipped, "
            "(a)ll (except passed), "
            "(A)ll.  [default: dftnrs]",
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
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--all",
            "-a",
            dest="show_all",
            action="store_true",
            default=False,
            help="Show all jobs regardless of status (overrides default failures-only filter for large runs)",
        )
        group.add_argument(
            "--failed",
            dest="show_failed_only",
            action="store_true",
            default=False,
            help="Show only failed/not-pass jobs (always uses the failures filter, even for small runs)",
        )
        parser.add_argument(
            "specs", nargs=argparse.REMAINDER, help="Show status history for these specific specs"
        )

    def execute(self, args: "argparse.Namespace") -> int:
        """Load workspace results and print the status table or JSON output, returning 0."""
        if args.specs:
            self.print_spec_status_history(args.specs, args)
            return 0
        results = app.get_results()

        if getattr(args, "output_json", False):
            self.print_json(results, args)
            return 0

        all_rows = sorted(results.values(), key=sortkey)
        total = len(all_rows)
        show_all: bool = getattr(args, "show_all", False)
        show_failed_only: bool = getattr(args, "show_failed_only", False)
        user_cols: str | None = args.format_cols  # None means "use smart default"

        # Determine which rows to show in the detail table.
        if show_failed_only:
            # Explicit --failed: always failures-only.
            detail_rows = filter_by_status(all_rows, args.report_chars)
            cols = user_cols or _DEFAULT_COLS_FULL
        elif show_all or total <= _AUTO_EXPAND_THRESHOLD:
            # --all flag or small run: show every row with concise columns.
            detail_rows = filter_by_status(all_rows, "A")
            cols = user_cols or _DEFAULT_COLS_CONCISE
        else:
            # Large run default: failures/diffs/timeouts/not-run/skipped only.
            detail_rows = filter_by_status(all_rows, args.report_chars)
            cols = user_cols or _DEFAULT_COLS_FULL

        # Inject the resolved column choice so get_status_table_from_rows picks it up.
        args.format_cols = cols

        # Build outcome counts for the summary line.
        summary_line = _build_summary_line(all_rows)

        console = Console()

        if total == 0:
            console.print("[dim]No results found in workspace.[/dim]")
            return 0

        # Always print the summary line first.
        console.print(summary_line)

        if not detail_rows:
            # All jobs passed (or nothing matched the filter) — nothing more to print.
            return 0

        # For large runs (non-all, non-small), print the analyst-friendly failure
        # grouping summary before the raw table.
        show_failure_summary = (
            not show_all
            and total > _AUTO_EXPAND_THRESHOLD
            and not getattr(args, "output_json", False)
        )
        if show_failure_summary:
            non_pass = [r for r in all_rows if not r["status"].is_success()]
            if non_pass:
                console.print(_build_failure_summary(non_pass))

        table = self.get_status_table_from_rows(detail_rows, args)
        from ..util.pager import page_rich

        page_rich(console, table, table.row_count)
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
            state: JobState = row["state"]
            out.append(
                {
                    "id": sid,
                    "name": row["spec_name"],
                    "fullname": row["spec_fullname"],
                    "file_path": row.get("file_path", ""),
                    "session": row["session"],
                    "exit_code": status.code,
                    "phase": state.phase.value,
                    "running": state.is_running(),
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
        return self.get_status_table_from_rows(rows, args)

    def get_status_table_from_rows(self, rows: list[dict], args: "argparse.Namespace") -> Table:
        """Build a Rich ``Table`` from a pre-filtered list of result rows."""
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
        table = Table(expand=False, box=box.SQUARE)
        for col in ["Name", "ID", "Session", "Exit Code", "Duration", "Status", "Details"]:
            table.add_column(col)
        for id in ids:
            results = app.get_result_history(id)
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


def _build_summary_line(rows: list[dict]) -> str:
    """Return a Rich-markup summary string for *rows*, e.g. ``"5 jobs: 3 passed, 2 failed"``.

    Always non-empty. When everything passes the line is green; when there are
    failures it names each non-pass category.
    """
    from ..core.status import Outcome

    total = len(rows)
    counts: dict[str, int] = {}
    for row in rows:
        status: _Status = row["status"]
        state: JobState = row["state"]
        if status.is_success():
            key = "passed"
        elif status.is_skipped():
            key = "skipped"
        elif status.is_diffed():
            key = "diffed"
        elif status.is_timeout():
            key = "timeout"
        elif status.outcome in (Outcome.FAILED, Outcome.ERROR, Outcome.BROKEN):
            key = "failed"
        elif state.is_running():
            key = "running"
        elif not state.is_done():
            key = "not run"
        elif status.is_cancelled():
            key = "cancelled"
        else:
            key = "other"
        counts[key] = counts.get(key, 0) + 1

    job_word = "job" if total == 1 else "jobs"
    passed = counts.get("passed", 0)

    if passed == total:
        return f"[green]{total} {job_word}: {total} passed[/green]"

    parts: list[str] = []
    if passed:
        parts.append(f"[green]{passed} passed[/green]")
    for key in (
        "failed",
        "diffed",
        "timeout",
        "running",
        "skipped",
        "not run",
        "cancelled",
        "other",
    ):
        n = counts.get(key, 0)
        if n:
            color = (
                "red"
                if key in ("failed",)
                else "yellow"
                if key in ("diffed", "timeout")
                else "cyan"
                if key in ("running",)
                else "dim"
            )
            parts.append(f"[{color}]{n} {key}[/{color}]")
    detail = ", ".join(parts)
    return f"[bold]{total} {job_word}:[/bold] {detail}"


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
        state: JobState = row["state"]
        status: _Status = row["status"]
        if state.is_running() and status.is_unset():
            return "[cyan]RUNNING[/cyan]"
        return status.display_name(style="rich")
    elif attr == "status_reason":
        return row["status"].reason or ""
    raise AttributeError(attr)


def _group_failures(rows: list[dict]) -> list[tuple[str, str | None, list[dict]]]:
    """Group non-pass rows by ``(outcome_name, reason)`` for the failure summary.

    Returns a list of ``(outcome_label, reason, matching_rows)`` tuples sorted
    by descending group size.  BLOCKED rows are handled specially: their reason
    is replaced with a human-readable "upstream dependency failed" message that
    names the upstream job when the reason string contains one.
    """
    from ..core.status import Outcome

    groups: dict[tuple[str, str | None], list[dict]] = {}
    for row in rows:
        status: _Status = row["status"]
        outcome_name = status.outcome.name if status.outcome is not None else "UNKNOWN"
        reason: str | None = status.reason or None

        # Normalise BLOCKED reason: the raw reason can be a long internal string;
        # extract the upstream name if present, otherwise use a generic label.
        if status.outcome == Outcome.BLOCKED:
            if reason and ("failed" in reason.lower() or "blocked" in reason.lower()):
                # Keep it but trim to a reasonable length
                reason = reason[:120] if reason and len(reason) > 120 else reason
            else:
                reason = "upstream dependency failed"

        key = (outcome_name, reason)
        groups.setdefault(key, []).append(row)

    return sorted(((k[0], k[1], v) for k, v in groups.items()), key=lambda kv: -len(kv[2]))


def _build_failure_summary(rows: list[dict]) -> str:
    """Return a Rich-markup failure-summary block for *rows* (non-pass results).

    Groups failures by ``(outcome, reason)`` and shows the job names in each
    group.  Includes hint lines for the next actions an analyst should take.
    """
    groups = _group_failures(rows)
    total = len(rows)
    noun = "job" if total == 1 else "jobs"

    lines: list[str] = [f"[bold]Failure summary[/bold] ({total} {noun}):"]
    for outcome, reason, group_rows in groups:
        count = len(group_rows)
        names = ", ".join(r["spec_name"] for r in group_rows[:4])
        if count > 4:
            names += f", … (+{count - 4} more)"
        outcome_color = {
            "FAILED": "red",
            "ERROR": "red",
            "BROKEN": "red",
            "TIMEOUT": "yellow",
            "DIFFED": "yellow",
            "BLOCKED": "dim",
            "CANCELLED": "dim",
            "INTERRUPTED": "dim",
        }.get(outcome, "dim")
        outcome_label = f"[{outcome_color}]{outcome}[/{outcome_color}]"
        reason_str = f'  "[italic]{reason}[/italic]"' if reason else ""
        lines.append(f"  {outcome_label}{reason_str}  ×{count}   {names}")

    lines.append("")
    lines.append("  To view a job's output:  [bold]canary log[/bold] [dim]<ID>[/dim]")
    lines.append("  To rerun failures:       [bold]canary run --only failed[/bold]")
    return "\n".join(lines)


class ReportCharAction(argparse.Action):
    """Validate and store the ``-r`` report-character filter string."""

    chars = "pftdfnrsxaA"

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
    from ..core.status import Outcome

    chars = chars or "dftnrs"
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
        elif state.is_running():
            keep[i] = "r" in chars
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
