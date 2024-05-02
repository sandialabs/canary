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


description = "Run the analysis section of tests by passing \
    ``--execute-analysis-sections`` to their command line"
epilog = """\
An "analyze" run only makes sense in the following conditions:

1. The test has already been run; and
2. The test has logic for handling ``--execute-analysis-sections`` on the command line
"""


def setup_parser(parser: "Parser"):
    parser.add_argument("pathspec", nargs="?", help="Limit analyis to tests in this path")


def analyze(args: "argparse.Namespace") -> int:
    session = Session(os.getcwd(), mode="r")
    cases: list[TestCase]
    if args.pathspec:
        cases = filter_cases_by_path(session.cases, args.pathspec)
    else:
        cases = filter_cases_by_status(session.cases, ("failed", "diffed", "success"))
    for case in cases:
        logging.info(f"Executing analysis section of {case.pretty_repr()}")
        case.do_analyze()
    return 0
