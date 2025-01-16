import argparse
import os

from _canary.config.argparsing import Parser
from _canary.session import Session
from _canary.util import logging

from .base import Command


class Status(Command):
    @property
    def description(self) -> str:
        return "Print information about a test run"

    @property
    def epilog(self) -> str | None:
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
            "--sort-by",
            default="name",
            choices=("duration", "name"),
            help="Sort cases by this field [default: %(default)s]",
        )
        parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")

    def execute(self, args: "argparse.Namespace") -> int:
        session = Session(os.getcwd(), mode="r")
        rc: str
        if not args.report_chars:
            rc = "dftns"
        else:
            rc = "".join(args.report_chars)
        report = session.report(rc, sortby=args.sort_by, durations=args.durations)
        logging.emit(report)
        return 0
