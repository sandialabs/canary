import argparse
from typing import TYPE_CHECKING

from ..session import Session
from ..test.case import TestCase
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
    parser.add_argument("pathspec", nargs="?", help="Limit rebaselining to this path")


def analyze(args: "argparse.Namespace") -> int:
    session = Session.load(mode="r")
    cases: list[TestCase]
    if args.pathspec:
        cases = filter_cases_by_path(session.cases, args.pathspec)
    else:
        cases = filter_cases_by_status(session.cases, ("failed", "diffed", "success"))
    for case in cases:
        case.do_analyze()
    return 0
