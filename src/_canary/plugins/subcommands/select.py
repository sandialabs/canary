# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...util import logging
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Select())


class Select(CanarySubcommand):
    name = "select"
    description = "Make a tagged selection"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-k",
            dest="keyword_exprs",
            metavar="expression",
            action="append",
            help="Only run tests matching given keyword expression. "
            "For example: `-k 'key1 and not key2'`.  The keyword ``:all:`` matches all tests",
        )
        parser.add_argument(
            "-o",
            dest="on_options",
            default=None,
            metavar="option",
            action="append",
            help="Turn option(s) on, such as '-o dbg' or '-o intel'",
        )
        parser.add_argument(
            "-p",
            dest="parameter_expr",
            metavar="expression",
            help="Filter tests by parameter name and value, such as '-p cpus=8' or '-p cpus<8'",
        )
        parser.add_argument(
            "--search",
            "--regex",
            dest="regex_filter",
            metavar="regex",
            help="Include tests containing the regular expression regex in at least 1 of its "
            "file assets.  regex is a python regular expression, see "
            "https://docs.python.org/3/library/re.html",
        )
        parser.add_argument(
            "-r", action="append", dest="select_paths", help="Select tests found in these paths"
        )
        parser.add_argument("-t", "--tag", required=True, help="Tag this selection with TAG")

    def execute(self, args: "argparse.Namespace") -> int:
        workspace: Workspace = Workspace.load()
        workspace.make_selection(
            tag=args.tag,
            paths=args.select_paths,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
        )
        logger.info(f"To run this selection execute 'canary run {args.tag}'")
        return 0
