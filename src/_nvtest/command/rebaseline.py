import argparse
import os
from typing import TYPE_CHECKING

from ..session import Session
from ..test.case import TestCase
from ..util import logging
from .common import filter_cases_by_path
from .common import filter_cases_by_status

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Rebaseline tests"


def setup_parser(parser: "Parser"):
    parser.add_argument("pathspec", nargs="?", help="Limit rebaselining to this path")


def rebaseline(args: "argparse.Namespace") -> int:
    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    cases: list[TestCase]
    if args.pathspec:
        cases = filter_cases_by_path(session.cases, args.pathspec)
    else:
        cases = filter_cases_by_status(session.cases, ("failed", "diffed"))
    for case in cases:
        case.do_baseline()
    return 0
