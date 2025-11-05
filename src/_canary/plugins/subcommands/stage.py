# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...util import logging
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Tag())


class Tag(CanarySubcommand):
    name = "tag"
    description = "The the selection criteria"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser, tagged=False)
        parser.add_argument("tag", help="Tag this selection with TAG")

    def execute(self, args: "argparse.Namespace") -> int:
        workspace: Workspace = Workspace.load()
        workspace.tag(
            args.tag,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
        )
        logger.info(f"To run this tag execute 'canary run {args.tag}'")
        return 0
