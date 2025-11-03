# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from ...repo import Repo
from ...util import logging
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Lock())


class Lock(CanarySubcommand):
    name = "lock"
    description = "Generate (lock) test cases for the given selection criteria"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser)
        parser.add_argument("--tag", help="Given selection this tag")
        parser.add_argument(
            "start",
            default=None,
            nargs="?",
            help="Lock only test cases in this path (and its subdirectories)",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        repo: Repo = Repo.load(Path.cwd())
        repo.lock(
            tag=args.tag,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
            start=args.start,
        )
        return 0
