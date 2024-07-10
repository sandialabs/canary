import os
from typing import TYPE_CHECKING

from ..session import Session
from ..util import logging

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Show the test case's log file"
epilog = "Note: this command must be run from inside of a test session directory."


def setup_parser(parser: "Parser"):
    parser.add_argument("testspec", help="Test name, /TEST_ID, or ^BATCH_LOT:BATCH_NO")


def log(args: "argparse.Namespace") -> int:
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
