import os
from typing import TYPE_CHECKING

from ..session import Session
from ..util import logging

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Show test properties"


def setup_parser(parser: "Parser"):
    parser.add_argument("testspec", help="Test name or test id")


def show(args: "argparse.Namespace") -> int:
    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    for case in session.cases:
        if case.matches(args.testspec):
            d = dict(vars(case))
            d["status"] = (case.status.value, case.status.details)
            d["logfile"] = case.logfile()
            print(case)
            for key in sorted(d):
                print(f"  {key}: {d[key]}")
            return 0
    raise ValueError(f"{args.testspec}: no matching test found in {session.root}")
