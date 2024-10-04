import argparse
import os
from typing import Optional

from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.util import logging


class Log(Command):
    @property
    def description(self) -> str:
        return "Show the test case's log file"

    @property
    def epilog(self) -> Optional[str]:
        return "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: Parser):
        parser.add_argument("testspec", help="Test name, /TEST_ID, or ^BATCH_LOT:BATCH_NO")

    def execute(self, args: argparse.Namespace) -> int:
        import pydoc

        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")

        if args.testspec.startswith("^"):
            lot_no, batch_no = [int(_) for _ in args.testspec[1:].split(":")]
            file = session.blogfile(batch_no, lot_no=lot_no)
            print(f"{file}:")
            pydoc.pager(open(file).read())
            return 0
        else:
            for case in session.cases:
                if case.matches(args.testspec):
                    f: str = case.logfile()
                    if not os.path.isfile(f):
                        raise ValueError(f"{f}: no such file")
                    print(f"{f}:")
                    pydoc.pager(open(f).read())
                    return 0
        raise ValueError(f"{args.testspec}: no matching test found in {session.root}")
