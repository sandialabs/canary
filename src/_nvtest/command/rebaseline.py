import argparse
import os
from typing import TYPE_CHECKING

from ..session import Session
from ..test.enums import Result
from ..util import tty
from ..util.filesystem import copyfile

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..test.testcase import TestCase


description = "Rebaseline tests"


def setup_parser(parser: "Parser"):
    parser.add_argument("pathspec", nargs="?", help="Limit rebaselining to this path")


def matches(case: "TestCase", pathspec: str) -> bool:
    if pathspec.startswith("/") and case.id.startswith(pathspec[1:]):
        return True
    if pathspec == case.display_name:
        return True
    if case.exec_dir.startswith(os.path.abspath(pathspec)):
        return True
    return False


def rebaseline(args: "argparse.Namespace") -> int:
    session = Session.load(mode="r")
    cases = [c for c in session.cases if c.result != Result.NOTRUN]
    if args.pathspec:
        cases = [c for c in cases if matches(c, args.pathspec)]
    for case in cases:
        if not case.baseline:
            tty.warn(f"{case.pretty_repr()} does not define rebaselining instructions")
            continue
        tty.info(f"Rebaselining {case.pretty_repr()}")
        for a, b in case.baseline:
            src = os.path.join(case.exec_dir, a)
            dst = os.path.join(case.file_dir, b)
            if os.path.exists(src):
                tty.print(f"    Replacing {b} with {a}")
                copyfile(src, dst)
    return 0
