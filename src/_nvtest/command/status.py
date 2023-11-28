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
    parser.add_argument(
        "-l",
        dest="show_logs",
        action="store_true",
        default=False,
        help="Show log file location as well as names [default: %(default)s]",
    )
    parser.add_argument(
        "-p",
        dest="show_pass",
        action="store_true",
        default=False,
        help="Show tests that passed [default: %(default)s]",
    )
    parser.add_argument(
        "-t",
        dest="show_timeout",
        action="store_true",
        default=False,
        help="Show tests that timed out [default: %(default)s]",
    )
    parser.add_argument(
        "-d",
        dest="show_diff",
        action="store_true",
        default=False,
        help="Show tests that diffed [default: %(default)s]",
    )
    parser.add_argument(
        "-f",
        dest="show_fail",
        action="store_true",
        default=False,
        help="Show tests that failed [default: %(default)s]",
    )
    parser.add_argument(
        "-n",
        dest="show_notrun",
        action="store_true",
        default=False,
        help="Show tests that were not run [default: %(default)s]",
    )
    parser.add_argument(
        "-s",
        dest="show_skip",
        action="store_true",
        default=False,
        help="Show tests that were skipped [default: %(default)s]",
    )
    parser.add_argument(
        "-a",
        dest="show_all",
        action="store_true",
        default=False,
        help="Show status for all tests (implies -ptdfn) [default: %(default)s]",
    )
    parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")


def matches(pathspec, case):
    return case.exec_root is not None and case.exec_dir.startswith(pathspec)


def status(args: "argparse.Namespace") -> int:
    work_tree = config.get("session:work_tree")
    if work_tree is None:
        tty.die("not a nvtest session (or any of the parent directories): .nvtest")
    session = Session.load(mode="r")
    cases = session.cases
    if args.pathspec:
        pathspec = os.path.abspath(args.pathspec)
        if pathspec != work_tree:
            cases = [c for c in cases if matches(pathspec, c)]
    for attr in (
        "show_fail",
        "show_diff",
        "show_timeout",
        "show_pass",
        "show_notrun",
        "show_skip",
    ):
        if getattr(args, attr):
            break
    else:
        args.show_all = True
    cases_to_show: list[TestCase] = []
    if args.show_all:
        cases_to_show = cases
    else:
        for case in cases:
            if args.show_skip and case.skip:
                cases_to_show.append(case)
            elif args.show_pass and case.result == Result.PASS:
                cases_to_show.append(case)
            elif args.show_fail and case.result == Result.FAIL:
                cases_to_show.append(case)
            elif args.show_diff and case.result == Result.DIFF:
                cases_to_show.append(case)
            elif args.show_timeout and case.result == Result.TIMEOUT:
                cases_to_show.append(case)
            elif args.show_notrun and case.result in (Result.NOTRUN, Result.NOTDONE):
                cases_to_show.append(case)
    if cases_to_show:
        print_status(cases_to_show, show_logs=args.show_logs)
    if args.durations is not None:
        print_durations(cases, int(args.durations))
    print_summary(cases)
    return 0


def cformat(case: TestCase, show_log: bool) -> str:
    id = tty.color.colorize("@*b{%s}" % case.id[:7])
    string = "%s %s %s (%.2f s.)" % (case.result.cname, id, str(case), case.duration)
    if show_log:
        f = os.path.relpath(case.logfile, os.getcwd())
        string += tty.color.colorize(": @m{%s}" % f)
    return string


def print_status(cases: list[TestCase], show_logs: bool = False) -> None:
    totals: dict[str, list[TestCase]] = {}
    for case in cases:
        totals.setdefault(case.result.name, []).append(case)
    if Result.NOTRUN in totals:
        for case in totals[Result.NOTRUN]:
            tty.print(cformat(case, show_logs))
    if Result.SETUP in totals:
        for case in totals[Result.SETUP]:
            tty.print(cformat(case, show_logs))
    if Result.PASS in totals:
        for case in totals[Result.PASS]:
            tty.print(cformat(case, show_logs))
    for result in (Result.FAIL, Result.DIFF, Result.TIMEOUT):
        if result not in totals:
            continue
        for case in totals[result]:
            tty.print(cformat(case, show_logs))
    if Result.NOTDONE in totals:
        for case in totals[Result.NOTDONE]:
            tty.print(cformat(case, show_logs))
    if Result.SKIP in totals:
        for case in totals[Result.SKIP]:
            cname = case.result.cname
            reason = case.skip.reason
            tty.print("%s %s: Skipped due to %s" % (cname, str(case), reason))


def print_summary(cases: list[TestCase]) -> None:
    totals: dict[str, list[TestCase]] = {}
    for case in cases:
        totals.setdefault(case.result.name, []).append(case)
    summary_parts = []
    colorize = tty.color.colorize
    for member in Result.members:
        n = len(totals.get(member, []))
        if n:
            c = Result.colors[member]
            summary_parts.append(colorize("@%s{%d %s}" % (c, n, member.lower())))
    tty.print(", ".join(summary_parts), centered=True)


def print_durations(cases: list[TestCase], N: int) -> None:
    cases = [case for case in cases if case.duration > 0]
    sorted_cases = sorted(cases, key=lambda x: x.duration)
    if N > 0:
        sorted_cases = sorted_cases[-N:]
    tty.print(f"\nSlowest {len(sorted_cases)} durations\n")
    for case in sorted_cases:
        tty.print("  %6.2f     %s" % (case.duration, str(case)))
