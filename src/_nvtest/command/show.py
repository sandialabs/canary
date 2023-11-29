import os
from typing import TYPE_CHECKING

from .. import config
from ..session import Session
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
    group.add_argument(
        "-d",
        dest="show_exec_dir",
        action="store_true",
        default=False,
        help="Show the path to the test's execution directory",
    )
    group.add_argument(
        "-D",
        dest="show_source_dir",
        action="store_true",
        default=False,
        help="Show the path to the test's source directory",
    )
    parser.add_argument("testspec", help="Test name or test id")
    parser.epilog = "If no options are give, -l is assumed"


def show(args: "argparse.Namespace") -> int:
    import pydoc

    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")

    session = Session.load(mode="r")
    for case in session.cases:
        if case.matches(args.testspec):
            f: str = case.logfile
            if args.show_input:
                f = case.file
            elif args.show_exec_dir:
                f = case.exec_dir
            elif args.show_source_dir:
                f = case.file_dir
            if os.path.isfile(f):
                pydoc.pager(open(f).read())
            else:
                print(f)
            return 0
    tty.die(f"{args.testspec}: no matching test found in {work_tree}")
    return 1
