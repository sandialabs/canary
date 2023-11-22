import argparse
import os
from typing import TYPE_CHECKING

from ..config import Config
from ..session import Session
from ..test.enums import Result
from ..util.filesystem import copyfile

if TYPE_CHECKING:
    from ..config.argparsing import Parser


description = "Rebaseline tests"


def setup_parser(parser: "Parser"):
    parser.add_argument("path", help="Rebaseline tests found at PATH")


def rebaseline(config: "Config", args: "argparse.Namespace") -> int:
    start = os.path.abspath(args.path)
    workdir = Session.find_workdir(start)
    session = Session.load(workdir=workdir, config=config)
    cases = [
        c
        for c in session.cases
        if c.result != Result.NOTRUN and c.exec_dir.startswith(start)
    ]
    for case in cases:
        if not case.baseline:
            continue
        for (a, b) in case.baseline:
            src = os.path.join(case.exec_dir, a)
            dst = os.path.join(case.file_dir, b)
            if os.path.exists(src):
                copyfile(src, dst)
    return 0
