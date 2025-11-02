# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
import sys
from typing import TYPE_CHECKING

from ... import config
from ...util import graph
from ...util import logging
from ...repo import NotARepoError
from ...repo import Repo
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments

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
            help="Lock only test cases in this path (and its subdirectories)"
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
