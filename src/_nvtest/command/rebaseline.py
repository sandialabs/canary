import argparse
import os
from typing import TYPE_CHECKING
from typing import Union

from ..session import Session
from ..test.testcase import TestCase

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Rebaseline tests"


def setup_parser(parser: "Parser"):
    parser.add_argument("pathspec", nargs="?", help="Limit rebaselining to this path")


def rebaseline(args: "argparse.Namespace") -> int:
    session = Session.load(mode="r")
    cases = filter_cases(session.cases, args.pathspec)
    for case in cases:
        case.do_baseline()
    return 0


def filter_cases(cases: list[TestCase], pathspec: Union[str, None]) -> list[TestCase]:
    filtered_cases: list[TestCase]
    if pathspec is None:
        filtered_cases = [c for c in cases if c.status.value in ("failed", "diffed")]
    else:
        prefix = os.path.abspath(pathspec)
        filtered_cases = [
            c for c in cases if c.matches(pathspec) or c.exec_dir.startswith(prefix)
        ]
    return filtered_cases
