import os
from typing import TYPE_CHECKING

from ..session import Session
from ..test.enums import Result
from ..test.testcase import TestCase
from ..util import tty

if TYPE_CHECKING:
    import argparse

    from ..config import Config
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
    parser.add_argument(
        "workdir", nargs="?", default=os.getcwd(), help="Test results directory"
    )


def status(config: "Config", args: "argparse.Namespace") -> int:
    try:
        workdir = Session.find_workdir(args.workdir)
    except ValueError:
        tty.die(f"{args.workdir!r} is not a test execution directory")
    args.mode = "r"
    session = Session.load(config=config, workdir=workdir, mode=args.mode)
    start = workdir if args.workdir is None else os.path.abspath(args.workdir)
    cases = [c for c in session.cases if not c.skip]
    if start != workdir:
        cases = [
            c for c in cases if c.exec_root is not None and c.exec_dir.startswith(start)
        ]
    if not cases:
        tty.info("Nothing to report")
        return 0
    tty.print(f"\nTest execution directory: {start}\n")
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
