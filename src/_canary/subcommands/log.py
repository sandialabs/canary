# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary log`` subcommand for viewing session or job log files."""

import argparse
import datetime
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING

from .. import app
from ..hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..core.job import Job


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Log())


class Log(CanarySubcommand):
    """Display the session log or a specific job's stdout, stderr, or workspace file."""

    name = "log"
    description = "Show the session or a job's log file"

    def setup_parser(self, parser: "Parser") -> None:
        """Register ``testspec``, ``-e/--error``, ``-l/--lock``, ``-f/--file``, ``--tail``, and ``--raw`` arguments."""
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "-e",
            "--error",
            default=False,
            action="store_true",
            help="Display test stderr if it exists",
        )
        group.add_argument(
            "-l",
            "--lock",
            dest="workspace_file",
            action="store_const",
            const="testcase.lock",
            default=None,
            help="Display test lockfile if it exists; equivalent to -f testcase.lock",
        )
        group.add_argument(
            "-f",
            "--file",
            dest="workspace_file",
            metavar="PATH",
            help="Display PATH from the test's workspace",
        )
        parser.add_argument(
            "--tail",
            metavar="N",
            type=int,
            default=None,
            help="Show only the last N lines of the log file (useful for finding errors quickly)",
        )
        parser.add_argument(
            "--raw",
            default=False,
            action="store_true",
            help="Show raw log file contents (applicable only to the session log file)",
        )
        parser.add_argument(
            "testspec",
            nargs="?",
            help="Test name or TEST_ID.  If not given, the session log will be shown",
        )

    def get_file_from_workspace(self, job: "Job", args: argparse.Namespace) -> Path | None:
        """Resolve which workspace file to display for *job* based on the parsed flags.

        Args:
            job: The job whose workspace is inspected.
            args: Parsed namespace; checks ``args.error`` and ``args.workspace_file``.

        Returns:
            Absolute path to the file to display, or ``None`` if not applicable.
        """
        if args.error:
            if job.stderr is None:
                return None
            return job.workspace.joinpath(job.stderr)
        if args.workspace_file:
            return job.workspace.joinpath(args.workspace_file)
        return job.workspace.joinpath(job.stdout)

    def execute(self, args: argparse.Namespace) -> int:
        """Display the session log or a specific job log file, paging if needed."""
        workspace = app.open_workspace()

        if not args.testspec:
            file = workspace.logs_dir / "canary.0.log"
            if file.exists():
                text: str
                if args.raw:
                    text = open(file).read()
                else:
                    text = reconstruct_log(file)
                if args.tail is not None:
                    text = tail_text(text, args.tail)
                page_text(text)
                return 0
            raise ValueError(f"no log file found in {workspace.root}")

        job = workspace.find(job=args.testspec)
        f = self.get_file_from_workspace(job, args)
        if f:
            display_file(f, tail=args.tail)
        return 0


def reconstruct_log(file: str | Path) -> str:
    """Read a JSONL log file and return its records reformatted chronologically."""
    file = Path(file)
    fp = io.StringIO()
    if not file.is_file():
        raise ValueError(f"{file}: no such file")
    fmt = "[%(time)s] %(level)s: %(message)s\n"
    records: list[dict[str, str]] = []
    for line in open(file):
        record = json.loads(line)
        records.append(record)
    for record in sorted(records, key=lambda x: datetime.datetime.fromisoformat(x["time"])):
        fp.write(fmt % record)
    return fp.getvalue()


def tail_text(text: str, n: int) -> str:
    """Return the last *n* lines of *text*, preserving the trailing newline."""
    lines = text.splitlines()
    tail = lines[-n:] if n > 0 and len(lines) > n else lines
    skipped = len(lines) - len(tail)
    result = "\n".join(tail)
    if skipped > 0:
        result = (
            f"[... {skipped} lines omitted — use canary log without --tail to see all ...]\n"
            + result
        )
    return result


def display_file(file: Path, *, tail: int | None = None) -> None:
    """Print *file*'s path header and page its contents, raising if the file is missing."""
    if not file.exists():
        raise FileNotFoundError(file)
    text = file.read_text().rstrip()
    if tail is not None:
        text = tail_text(text, tail)
    print(f"{file}:")
    page_text(text)


def page_text(text: str) -> None:
    """Page *text* through a pager when appropriate, otherwise write directly."""
    from ..util.pager import page

    page(text)
