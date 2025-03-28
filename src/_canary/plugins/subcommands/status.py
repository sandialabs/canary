# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...util import logging
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Status()


class Status(CanarySubcommand):
    name = "status"
    description = "Print information about a test run"
    epilog = "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: "Parser"):
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
        session = load_session()
        rc: str
        if not args.report_chars:
            rc = "dftns"
        else:
            rc = "".join(args.report_chars)
        report = session.report(rc, sortby=args.sort_by, durations=args.durations)
        logging.emit(report)
        return 0
