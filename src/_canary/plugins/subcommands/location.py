import argparse
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Location()


class Location(CanarySubcommand):
    name = "location"
    description = "Print locations of test files and directories"
    epilog = """\
If no options are give, -x is assumed.

Note: this command must be run from inside of a test session directory.
"""

    def setup_parser(self, parser: "Parser") -> None:
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
            dest="show_working_directory",
            action="store_true",
            default=False,
            help="Show the location of the test's working directory",
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
        session = load_session()

        for case in session.cases:
            if case.matches(args.testspec):
                f: str
                if args.show_log:
                    f = case.logfile()
                elif args.show_input:
                    f = case.file
                elif args.show_source_dir:
                    f = case.file_dir
                elif args.show_working_directory:
                    f = case.working_directory
                else:
                    f = case.working_directory
                print(f)
                return 0
        raise ValueError(f"{args.testspec}: no matching test found in {session.work_tree}")
