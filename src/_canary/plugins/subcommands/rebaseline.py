# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...util import logging
from ...util.banner import banner
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Rebaseline()


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    aliases = ["baseline"]
    description = "Rebaseline tests"

    def setup_parser(self, parser: "Parser") -> None:
        parser.epilog = self.in_session_note()
        add_filter_arguments(parser)
        PathSpec.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        from ...session import Session

        if getattr(args, "work_tree", None) is None:
            raise ValueError("rebaseline must be executed in a canary work tree")

        if not args.keyword_exprs and not args.start and not args.parameter_expr:
            # Rebaseline diffed tests by default
            args.keyword_exprs = "diff"

        logging.emit(banner() + "\n")
        session = Session(args.work_tree, mode="r")
        session.filter(
            start=args.start,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            case_specs=getattr(args, "case_specs", None),
        )
        for case in session.active_cases():
            case.do_baseline()
        return 0
