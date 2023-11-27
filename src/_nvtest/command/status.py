import os
from typing import TYPE_CHECKING

from .. import config
from ..session import Session
from ..test.enums import Result
from ..test.testcase import TestCase
from ..util import tty

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Print information about a test run"
aliases = ["stat"]


def setup_parser(parser: "Parser"):
    parser.add_argument(
        "--durations",
        type=int,
        metavar="N",
        help="Show N slowest test durations (N=0 for all)",
    )
    parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")


def matches(pathspec, case):
    return case.exec_root is not None and case.exec_dir.startswith(pathspec)


def status(args: "argparse.Namespace") -> int:
    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")
    session = Session.load(mode="r")
    cases = [c for c in session.cases if not c.skip]
    if args.pathspec:
        pathspec = os.path.abspath(args.pathspec)
        if pathspec != work_tree:
            cases = [c for c in cases if matches(pathspec, c)]
    if not cases:
        tty.info("Nothing to report")
        return 0
    tty.print(f"\nWork tree: {session.work_tree}")
    print_status(cases)
    if args.durations is not None:
        print_durations(cases, int(args.durations))
    tty.print()
    return 0


def cformat(case: TestCase) -> str:
    f = case.exec_dir
    if f.startswith(os.getcwd()):
        f = os.path.relpath(f)
    return "  %s %s: %s" % (case.result.cname, str(case), f)


def print_status(cases: list[TestCase]) -> None:
    totals: dict[str, list[TestCase]] = {}
    for case in cases:
        totals.setdefault(case.result.name, []).append(case)
    level = tty.get_log_level()
    tty.print()
    if level > tty.VERBOSE and Result.NOTRUN in totals:
        for case in totals[Result.NOTRUN]:
            tty.print(cformat(case))
    if level > tty.INFO and Result.SETUP in totals:
        for case in totals[Result.SETUP]:
            tty.print(cformat(case))
    if level > tty.INFO and Result.PASS in totals:
        for case in totals[Result.PASS]:
            tty.print(cformat(case))
    for result in (Result.FAIL, Result.DIFF, Result.TIMEOUT):
        if result not in totals:
            continue
        for case in totals[result]:
            tty.print(cformat(case))
    if Result.NOTDONE in totals:
        for case in totals[Result.NOTDONE]:
            tty.print(cformat(case))
    if Result.SKIP in totals:
        for case in totals[Result.SKIP]:
            cname = case.result.cname
            reason = case.skip.reason
            tty.print("%s %s: Skipped due to %s" % (cname, str(case), reason))


def print_durations(cases: list[TestCase], N: int) -> None:
    cases = [case for case in cases if case.duration > 0]
    sorted_cases = sorted(cases, key=lambda x: x.duration)
    if N > 0:
        sorted_cases = sorted_cases[-N:]
    tty.print(f"\nSlowest {len(sorted_cases)} durations\n")
    for case in sorted_cases:
        tty.print("  %6.2f     %s" % (case.duration, str(case)))
