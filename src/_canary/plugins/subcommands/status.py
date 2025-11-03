# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import itertools
import re
from typing import TYPE_CHECKING

from ... import status
from ...repo import Repo
from ...third_party import colify
from ...third_party.color import colorize
from ..hookspec import hookimpl
from ..types import CanarySubcommand

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
        table = repo.status()
        fh = io.StringIO()
        for row in table[2:]:
            row[0] = colorize("@*b{%s}" % row[0])
            row[1] = pretty_test_name(row[1])
            row[3] = colorize("@*{%s}" % row[3])  # duration
            row[5] = pretty_status_name(row[5])
        colify.colify_table(table, output=fh)
        print(fh.getvalue())
        return 0


def pretty_test_name(name: str) -> str:
    colors = itertools.cycle("bmgycr")
    if match := re.search(r"(\w+)\[(.*)\]", name):
        stem = match.group(1)
        params = match.group(2).split(",")
        string = ",".join("@%s{%s}" % (next(colors), p) for p in params)
        return colorize("%s[%s]" % (stem, string))
    return name


def pretty_status_name(name: str) -> str:
    color: str = ""
    fmt: str = "%(name)s"
    if name in ("created", "retry", "pending", "ready", "skipped"):
        color = status.Status.colors["created"]
        fmt = "@*%(color)s{not run} (%(name)s)"
    elif name in ("not_run",):
        color = status.Status.colors[name]
        fmt = "@*%(color)s{not run} (failed dependency)"
    elif name in ("diffed", "failed", "timeout", "invalid", "unknown"):
        color = status.Status.colors["failed"]
        fmt = "@*%(color)s{failed} (%(name)s)"
    else:
        color = status.Status.colors[name]
        fmt = "@*%(color)s{%(name)s}"
    return colorize(fmt % {"color": color, "name": name})


class ReportCharAction(argparse.Action):
    chars = "pftdfnsxaA"

    def __call__(self, parser, args, values, option_string=None):
        for value in values:
            if value not in self.chars:
                parser.error(f"Invalid report char {value!r}, choose any from {self.chars!r}")
        setattr(args, self.dest, values)
