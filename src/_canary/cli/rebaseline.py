# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from .. import app
from ..plugins.hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Rebaseline())


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    description = "Update baseline files from existing test results"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-k",
            dest="keyword_exprs",
            metavar="KEYWORD_EXPR",
            action="append",
            help="Restrict rebaseline to jobs matching keyword expression",
        )
        parser.add_argument(
            "targets",
            nargs="*",
            metavar="DIR_OR_JOBID",
            help=(
                "One or more results directories or job ids/names. "
                "Directories select the jobs whose results lie at or below them. "
                "Jobs selected by more than one target are rebaselined once. "
                "[default: current directory]"
            ),
        )

    def execute(self, args: argparse.Namespace) -> int:
        app.rebaseline(args.targets or ["."], keyword_exprs=args.keyword_exprs)
        return 0
