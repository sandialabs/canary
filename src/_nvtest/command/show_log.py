import pydoc
from typing import TYPE_CHECKING

from .. import config
from ..session import Session
from ..test.testcase import TestCase
from ..util import tty

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Show log file of completed test"


def setup_parser(parser: "Parser"):
    parser.add_argument("testspec", help="Test name or test id")


def show_log(args: "argparse.Namespace") -> int:
    def matches(case: TestCase):
        if case.id.startswith(args.testspec):
            return True
        if case.display_name == args.testspec:
            return True
        return False

    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")

    session = Session.load(mode="r")
    for case in session.cases:
        if matches(case):
            logfile = case.logfile
            pydoc.pager(open(logfile).read())
            return 0
    tty.die(f"{args.testspec}: no matching test found in {work_tree}")
    return 1
