# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Log()


class Log(CanarySubcommand):
    name = "log"
    description = "Show the test case's log file"

    def setup_parser(self, parser: "Parser") -> None:
        parser.epilog = self.in_session_note()
        parser.add_argument("testspec", help="Test name, /TEST_ID, or ^BATCH_ID")

    def execute(self, args: argparse.Namespace) -> int:
        import pydoc

        from ...test.batch import TestBatch
        from ...test.case import from_id as testcase_from_id

        file: str
        if args.testspec.startswith("/"):
            case = testcase_from_id(args.testspec[1:])
            file = case.logfile()
            if not os.path.isfile(file):
                file = case.logfile(stage="run")
            if not os.path.isfile(file):
                raise ValueError(f"{file}: no such file")
            print(f"{file}:")
            pydoc.pager(open(file).read())
            return 0

        if args.testspec.startswith("^"):
            file = TestBatch.logfile(args.testspec[1:])
            print(f"{file}:")
            if not os.path.isfile(file):
                raise ValueError(f"{file}: no such file")
            pydoc.pager(open(file).read())
            return 0

        session = load_session()
        for case in session.cases:
            if case.matches(args.testspec):
                file = case.logfile()
                if not os.path.isfile(file):
                    raise ValueError(f"{file}: no such file")
                print(f"{file}:")
                pydoc.pager(open(file).read())
                return 0

        raise ValueError(f"{args.testspec}: no matching test found in {session.work_tree}")
