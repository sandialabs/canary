import argparse
import glob
import json
import os

from ...config.argparsing import Parser
from ...test.batch import TestBatch
from ...test.case import TestCase
from ...test.case import from_state as testcase_from_state
from ...util.filesystem import find_work_tree
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return CanarySubcommand(
        name="log",
        description="Show the test case's log file",
        epilog=epilog,
        setup_parser=setup_parser,
        execute=log,
    )


epilog = "Note: this command must be run from inside of a test session directory."


def setup_parser(parser: Parser) -> None:
    parser.add_argument("testspec", help="Test name, /TEST_ID, or ^BATCH_ID")


def log(args: argparse.Namespace) -> int:
    import pydoc

    root = find_work_tree(os.getcwd())
    if root is None:
        raise ValueError("canary log must be executed in a test session")

    config_dir = os.path.join(root, ".canary")

    file: str
    if args.testspec.startswith("/"):
        id = args.testspec[1:]
        pat = os.path.join(config_dir, "objects", id[:2], f"{id[2:]}*", TestCase._lockfile)
        lockfiles = glob.glob(pat)
        if lockfiles:
            with open(lockfiles[0], "r") as fh:
                state = json.load(fh)
                case = testcase_from_state(state)
            file = case.logfile()
            if not os.path.isfile(file):
                file = case.logfile(stage="run")
            if not os.path.isfile(file):
                raise ValueError(f"{file}: no such file")
            print(f"{file}:")
            pydoc.pager(open(file).read())
            return 0

    elif args.testspec.startswith("^"):
        file = TestBatch.logfile(args.testspec[1:])
        print(f"{file}:")
        if not os.path.isfile(file):
            raise ValueError(f"{file}: no such file")
        pydoc.pager(open(file).read())
        return 0

    session = load_session()
    for case in session.cases:
        if case.matches(args.testspec):
            file = case.logfile()
            if not os.path.isfile(file):
                raise ValueError(f"{file}: no such file")
            print(f"{file}:")
            pydoc.pager(open(file).read())
            return 0

    raise ValueError(f"{args.testspec}: no matching test found in {session.work_tree}")
