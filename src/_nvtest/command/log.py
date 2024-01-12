import os
from typing import TYPE_CHECKING

from .. import config
from ..session import Session
from ..util import tty

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Show the test case's log file"


def setup_parser(parser: "Parser"):
    parser.add_argument("testspec", help="Test name or test id")


def log(args: "argparse.Namespace") -> int:
    import pydoc

    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")

    session = Session.load(mode="r")
    for case in session.cases:
        if case.matches(args.testspec):
            f: str = case.logfile()
            if not os.path.isfile(f):
                tty.die(f"{f}: no such file")
            print(f"{f}:")
            pydoc.pager(open(f).read())
            return 0
    tty.die(f"{args.testspec}: no matching test found in {work_tree}")
    return 1
