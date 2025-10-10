# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import datetime
import io
import json
import os
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Log()


class Log(CanarySubcommand):
    name = "log"
    description = "Show the session or a test case's log file"

    def setup_parser(self, parser: "Parser") -> None:
        parser.epilog = self.in_session_note()
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

    def get_logfile(self, case: "TestCase", args: argparse.Namespace) -> str:
        if args.error:
            return case.stderr_file or ""
        else:
            return case.stdout_file

    def execute(self, args: argparse.Namespace) -> int:
        from ...testcase import from_id as testcase_from_id

        file: str
        if not args.testspec:
            session = load_session(mode="r+")
            file = os.path.join(session.config_dir, "canary-log.txt")
            if os.path.exists(file):
                text: str
                if args.raw:
                    text = open(file).read()
                else:
                    text = reconstruct_log(file)
                page_text(text)
                return 0
            raise ValueError(f"no log file found in {session.config_dir}")

        if args.testspec.startswith("/"):
            case = testcase_from_id(args.testspec[1:])
            file = self.get_logfile(case, args)
            display_file(file)
            return 0

        session = load_session()
        for case in session.cases:
            if case.matches(args.testspec):
                file = self.get_logfile(case, args)
                display_file(file)
                return 0

        raise ValueError(f"{args.testspec}: no matching test found in {session.work_tree}")


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


def display_file(file: str) -> None:
    print(f"{file}:")
    if not os.path.isfile(file):
        raise ValueError(f"{file}: no such file")
    page_text(open(file).read())


def page_text(text: str) -> None:
    import pydoc

    pydoc.pager(text)
