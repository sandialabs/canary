# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import datetime
import io
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Log())


class Log(CanarySubcommand):
    name = "log"
    description = "Show the session or a test case's log file"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-e",
            "--error",
            default=False,
            action="store_true",
            help="Display test stderr if it exists",
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
            help="Test name or /TEST_ID.  If not given, the session log will be shown",
        )

    def get_logfile(self, case: "TestCase", args: argparse.Namespace) -> Path | None:
        if args.error:
            if case.stderr is None:
                return None
            return case.workspace.joinpath(case.stderr)
        else:
            return case.workspace.joinpath(case.stdout)

    def execute(self, args: argparse.Namespace) -> int:
        workspace = Workspace.load()

        if not args.testspec:
            file = workspace.logs_dir / "canary-log.txt"
            if file.exists():
                text: str
                if args.raw:
                    text = open(file).read()
                else:
                    text = reconstruct_log(file)
                page_text(text)
                return 0
            raise ValueError(f"no log file found in {workspace.root}")

        case = workspace.locate(case=args.testspec)
        file = self.get_logfile(case, args)
        if file:
            display_file(file)
        return 0


def reconstruct_log(file: str) -> str:
    fp = io.StringIO()
    if not os.path.isfile(file):
        raise ValueError(f"{file}: no such file")
    fmt = "[%(time)s] %(level)s: %(message)s\n"
    records: list[dict[str, str]] = []
    for line in open(file):
        record = json.loads(line)
        records.append(record)
    for record in sorted(records, key=lambda x: datetime.datetime.fromisoformat(x["time"])):
        fp.write(fmt % record)
    return fp.getvalue()


def display_file(file: Path) -> None:
    print(f"{file}:")
    if not file.exists():
        raise FileNotFoundError(file)
    page_text(file.read_text())


def page_text(text: str) -> None:
    import pydoc

    pydoc.pager(text)
