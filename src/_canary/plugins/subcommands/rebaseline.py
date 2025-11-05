# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import sys
from typing import TYPE_CHECKING

from ...util import logging
from ...util.banner import print_banner
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Rebaseline())


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    aliases = ["baseline"]
    description = "Rebaseline tests"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser)
        PathSpec.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        from ...workspace import Workspace

        if not args.keyword_exprs and not args.start and not args.parameter_expr:
            raise ValueError("At least one filtering criteria required")

        print_banner(sys.stderr)
        workspace = Workspace.load()
        cases = workspace.active_testcases()
        workspace.filter(
            cases,
            start=args.start,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            case_specs=getattr(args, "case_specs", None),
        )
        for case in cases:
            case.do_baseline()
        return 0
