import os
from typing import TYPE_CHECKING

from ..session import Session
from ..util import tty
from .run import print_front_matter
from .run import print_testcase_results

if TYPE_CHECKING:
    import argparse

    from ..config import Config
    from ..config.argparsing import Parser


description = "Print information about a test run"


def setup_parser(parser: "Parser"):
    parser.add_argument(
        "--durations",
        type=int,
        metavar="N",
        help="Show N slowest test durations (N=0 for all)",
    )
    parser.add_argument("workdir", nargs="?", help="Test results directory")


def info(config: "Config", args: "argparse.Namespace") -> int:
    try:
        workdir = Session.find_workdir(args.workdir or os.getcwd())
    except ValueError:
        tty.die(f"{args.workdir!r} is not a test execution directory")
    args.mode = "r"
    session = Session.load(config=config, workdir=workdir, mode=args.mode)
    tty.print("Test summary", centered=True)
    print_front_matter(config, args)
    start = workdir if args.workdir is None else os.path.abspath(args.workdir)
    cases = [c for c in session.cases if not c.skip]
    if start != workdir:
        cases = [
            c for c in cases if c.exec_root is not None and c.exec_dir.startswith(start)
        ]
    print_testcase_results(cases, durations=args.durations)
    return 0
