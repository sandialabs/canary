import argparse
import os
from typing import TYPE_CHECKING

from ..session import Session
from ..test.enums import Result
from ..util import tty
from ..util.filesystem import copyfile

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Rebaseline tests"


def setup_parser(parser: "Parser"):
    parser.add_argument("pathspec", nargs="?", help="Limit rebaselining to this path")


def rebaseline(args: "argparse.Namespace") -> int:
    session = Session.load(mode="r")
    cases = [c for c in session.cases if c.result != Result.NOTRUN]
    if args.pathspec:
        start = os.path.abspath(args.pathspec)
        cases = [c for c in cases if c.exec_dir.startswith(start)]
    for case in cases:
        if not case.baseline:
            continue
        for (a, b) in case.baseline:
            src = os.path.join(case.exec_dir, a)
            dst = os.path.join(case.file_dir, b)
            if os.path.exists(src):
                tty.info(f"Replacing {b} with {a}")
                copyfile(src, dst)
    return 0
