import os
from typing import TYPE_CHECKING

from ..session import Session
from ..test.case import TestCase
from ..util import logging

if TYPE_CHECKING:
    import argparse

    from ..config.argparsing import Parser


description = "Print information about a test run"
aliases = ["stat"]
epilog = "Note: this command must be run from inside of a test session directory."


def setup_parser(parser: "Parser"):
    parser.add_argument(
        "--durations",
        nargs="?",
        type=int,
        const=10,
        metavar="N",
        help="Show N slowest test durations (N<0 for all) [default: 10]",
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
        "-x",
        dest="show_excluded",
        action="store_true",
        default=False,
        help="Show tests that were excluded from " "initial test session [default: %(default)s]",
    )
    parser.add_argument(
        "-a",
        dest="show_all",
        action="store_true",
        default=False,
        help="Show status for all tests (implies -ptdfn) [default: %(default)s]",
    )
    parser.add_argument(
        "--sort-by",
        default="name",
        choices=("duration", "name"),
        help="Sort cases by this field [default: %(default)s]",
    )
    parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")
    parser.epilog = "-a is assumed if no other selection flags are passed"


def matches(pathspec, case):
    return case.exec_root is not None and case.exec_dir.startswith(pathspec)


def status(args: "argparse.Namespace") -> int:
    session = Session(os.getcwd(), mode="r")
    cases = session.cases
    if args.pathspec:
        if TestCase.spec_like(args.pathspec):
            cases = [c for c in cases if c.matches(args.pathspec)]
            args.show_all = True
        else:
            pathspec = os.path.abspath(args.pathspec)
            if pathspec != session.root:
                cases = [c for c in cases if c.exec_dir.startswith(pathspec)]
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
        args.show_pass = (
            args.show_diff
        ) = args.show_fail = args.show_timeout = args.show_notrun = True
    cases_to_show: list[TestCase] = []
    if args.show_all:
        if args.show_excluded:
            cases_to_show = cases
        else:
            cases_to_show = [case for case in cases if not case.mask]
    else:
        for case in cases:
            if case.mask:
                if args.show_excluded:
                    cases_to_show.append(case)
            elif args.show_skip and case.status == "skipped":
                cases_to_show.append(case)
            elif args.show_pass and case.status == "success":
                cases_to_show.append(case)
            elif args.show_fail and case.status == "failed":
                cases_to_show.append(case)
            elif args.show_diff and case.status == "diffed":
                cases_to_show.append(case)
            elif args.show_timeout and case.status == "timeout":
                cases_to_show.append(case)
            elif args.show_notrun and case.status.value in (
                "ready",
                "created",
                "pending",
                "cancelled",
            ):
                cases_to_show.append(case)
    if cases_to_show:
        logging.emit(session.status(cases_to_show, show_logs=args.show_logs, sortby=args.sort_by))
    if args.durations:
        logging.emit(session.durations(cases_to_show, int(args.durations)))
    logging.emit(session.footer(cases_to_show, title="Summary"))
    return 0
