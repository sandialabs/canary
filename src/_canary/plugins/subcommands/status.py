# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
import sys
from typing import TYPE_CHECKING

from ... import config
from ...repo import Repo
from ..builtin.reporting import determine_cases_to_show
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Status())


class Status(CanarySubcommand):
    name = "status"
    description = "Print information about a test run"

    def setup_parser(self, parser: "Parser"):
        parser.epilog = self.in_session_note()
        parser.add_argument(
            "--durations",
            nargs="?",
            type=int,
            const=10,
            metavar="N",
            help="Show N slowest test durations (N<0 for all) [default: 10]",
        )
        parser.add_argument(
            "--format",
            default="short",
            action="store",
            choices=["short", "long"],
            help="Change the format of the test case's name as printed to the screen. Options are 'short' and 'long' [default: %(default)s]",
        )
        parser.add_argument(
            "-r",
            dest="report_chars",
            action=ReportCharAction,
            default="dftns",
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
        parser.add_argument(
            "--dump", action="store_true", help="Dump test cases to lock lock file [default: False]"
        )
        parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")

    def execute(self, args: "argparse.Namespace") -> int:
        repo = Repo.load()
        repo.report_status(file=sys.stdout)
        return 0
        config.pluginmanager.hook.canary_statusreport(session=session)
        if args.dump:
            report_chars = args.report_chars or "dftns"
            cases_to_show = determine_cases_to_show(session, report_chars)
            cases = [case.getstate() for case in cases_to_show]
            file = os.path.join(config.invocation_dir, "testcases.lock")
            with open(file, "w") as fh:
                json.dump({"testcases": cases}, fh, indent=2)
        return 0


class ReportCharAction(argparse.Action):
    chars = "pftdfnsxaA"

    def __call__(self, parser, args, values, option_string=None):
        for value in values:
            if value not in self.chars:
                parser.error(f"Invalid report char {value!r}, choose any from {self.chars!r}")
        setattr(args, self.dest, values)
