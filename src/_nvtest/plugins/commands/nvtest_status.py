import argparse
import os
from typing import Optional

from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging


class Status(Command):
    @property
    def description(self) -> str:
        return "Print information about a test run"

    @property
    def aliases(self) -> list[str]:
        return ["stat"]

    @property
    def epilog(self) -> Optional[str]:
        return "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: Parser):
        parser.add_argument(
            "--durations",
            nargs="?",
            type=int,
            const=10,
            metavar="N",
            help="Show N slowest test durations (N<0 for all) [default: 10]",
        )
        parser.add_argument(
            "-r",
            dest="report_chars",
            action="append",
            choices=("p", "t", "d", "f", "n", "s", "x", "a", "A"),
            default=None,
            metavar="char",
            help="Show test summary info as specified by chars: "
            "(p)assed, "
            "(t)imeout "
            "(d)iffed, "
            "(f)ailed, "
            "(n)ot run, "
            "(s)kipped, "
            "e(x)cluded, "
            "(a)ll (except passed), "
            "(A)ll.  [default: dftns]",
        )
        parser.add_argument(
            "-l",
            dest="show_logs",
            action="store_true",
            default=False,
            help="Show log file location as well as names [default: %(default)s]",
        )
        parser.add_argument(
            "--sort-by",
            default="name",
            choices=("duration", "name"),
            help="Sort cases by this field [default: %(default)s]",
        )
        parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")

    def execute(self, args: "argparse.Namespace") -> int:
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
        attrs = {
            "f": "show_fail",
            "d": "show_diff",
            "t": "show_timeout",
            "p": "show_pass",
            "n": "show_notrun",
            "s": "show_skip",
            "a": "show_all_but_pass",
            "A": "show_all",
        }
        rc: str
        if not args.report_chars:
            rc = "dftns"
        else:
            rc = "".join(args.report_chars)
        cases_to_show: list[TestCase]
        if "A" in rc:
            if "x" in rc:
                cases_to_show = cases
            else:
                cases_to_show = [c for c in cases if not c.mask]
        elif "a" in rc:
            if "x" in rc:
                cases_to_show = [c for c in cases if c.status != "success"]
            else:
                cases_to_show = [c for c in cases if not c.mask and c.status != "success"]
        else:
            cases_to_show = []
            for case in cases:
                if case.mask:
                    if "x" in rc:
                        cases_to_show.append(case)
                elif "s" in rc and case.status == "skipped":
                    cases_to_show.append(case)
                elif "p" in rc and case.status.value in ("success", "xdiff", "xfail"):
                    cases_to_show.append(case)
                elif "f" in rc and case.status == "failed":
                    cases_to_show.append(case)
                elif "d" in rc and case.status == "diffed":
                    cases_to_show.append(case)
                elif "t" in rc and case.status == "timeout":
                    cases_to_show.append(case)
                elif "n" in rc and case.status.value in (
                    "ready",
                    "created",
                    "pending",
                    "cancelled",
                    "not_run",
                ):
                    cases_to_show.append(case)
        if cases_to_show:
            logging.emit(
                session.status(cases_to_show, show_logs=args.show_logs, sortby=args.sort_by)
            )
        if args.durations:
            logging.emit(session.durations(cases_to_show, int(args.durations)))
        logging.emit(session.footer(cases_to_show, title="Summary"))
        return 0
