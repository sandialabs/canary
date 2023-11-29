from typing import TYPE_CHECKING

from .. import config
from ..session import Session
from ..util import tty

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Print the location of test"


def setup_parser(parser: "Parser"):
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-s",
        "--source-dir",
        action="store_true",
        default=False,
        help="Show the location of the test's source",
    )
    group.add_argument(
        "-r",
        "--results-dir",
        action="store_true",
        default=False,
        help="Show the location of the test's results",
    )
    parser.add_argument("testspec", help="Test name or test id")


def location(args: "argparse.Namespace") -> int:
    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")

    session = Session.load(mode="r")
    for case in session.cases:
        if case.matches(args.testspec):
            if args.results_dir:
                print(case.exec_dir)
            else:
                print(case.file)
            return 0
    tty.die(f"{args.testspec}: no matching test found in {work_tree}")
    return 1
