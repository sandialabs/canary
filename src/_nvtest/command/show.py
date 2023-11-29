import pydoc
from typing import TYPE_CHECKING

from .. import config
from ..session import Session
from ..test.testcase import TestCase
from ..util import tty

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Show various types of objects"


def setup_parser(parser: "Parser"):
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-i",
        dest="show_input",
        action="store_true",
        default=False,
        help="Show the test's input file",
    )
    group.add_argument(
        "-l",
        dest="show_log",
        action="store_true",
        default=False,
        help="Show the test's log file",
    )
    parser.add_argument("testspec", help="Test name or test id")
    parser.epilog = "If no options are give, the log file is shown"


def matches(case: TestCase, testspec: str) -> bool:
    if case.id.startswith(testspec):
        return True
    if case.display_name == testspec:
        return True
    return False


def show(args: "argparse.Namespace") -> int:

    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")

    session = Session.load(mode="r")
    for case in session.cases:
        if matches(case, args.testspec):
            if args.show_input:
                f = case.file
            else:
                f = case.logfile
            pydoc.pager(open(f).read())
            return 0
    tty.die(f"{args.testspec}: no matching test found in {work_tree}")
    return 1
