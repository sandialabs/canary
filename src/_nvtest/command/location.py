import argparse
import os
from typing import Optional

from ..config.argparsing import Parser
from ..session import Session
from ..util import logging
from .command import Command


class Location(Command):
    @property
    def description(self) -> str:
        return "Print locations of test files and directories"

    @property
    def epilog(self) -> Optional[str]:
        return """\
If no options are give, -x is assumed.

Note: this command must be run from inside of a test session directory.
"""

    def setup_parser(self, parser: Parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "-i",
            dest="show_input",
            action="store_true",
            default=False,
            help="Show the location of the test's input file",
        )
        group.add_argument(
            "-l",
            dest="show_log",
            action="store_true",
            default=False,
            help="Show the location of the test's log file",
        )
        group.add_argument(
            "-x",
            dest="show_exec_dir",
            action="store_true",
            default=False,
            help="Show the location of the test's execution directory",
        )
        group.add_argument(
            "-s",
            dest="show_source_dir",
            action="store_true",
            default=False,
            help="Show the location of the test's source directory",
        )
        parser.add_argument("testspec", help="Test name or test id")

    def execute(self, args: argparse.Namespace) -> int:
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")

        for case in session.cases:
            if case.matches(args.testspec):
                f: str
                if args.show_log:
                    f = case.logfile()
                elif args.show_input:
                    f = case.file
                elif args.show_source_dir:
                    f = case.file_dir
                elif args.show_exec_dir:
                    f = case.exec_dir
                else:
                    f = case.exec_dir
                print(f)
                return 0
        raise ValueError(f"{args.testspec}: no matching test found in {session.root}")
