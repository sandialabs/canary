# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ...repo import Repo
from ...util import logging
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from ...util.banner import print_banner
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Stage())


class Stage(CanarySubcommand):
    name = "stage"
    description = "Generate test cases for the given selection criteria and store the selection for later running"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser, tagged=False)
        parser.add_argument("tag", help="Tag this selection with TAG")

    def execute(self, args: "argparse.Namespace") -> int:
        repo: Repo = Repo.load(Path.cwd())
        selection = repo.stage(
            tag=args.tag,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
        )
        logger.info(f"To run this collection of test cases, execute 'canary run {selection.tag}'")
        return 0
