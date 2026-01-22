# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...collect import Collector
from ...generate import Generator
from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Collect())


class Collect(CanarySubcommand):
    name = "collect"
    description = "Find and generate test cases"

    def setup_parser(self, parser: "Parser") -> None:
        Collector.setup_parser(parser)
        Generator.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        workspace.collect(args.scanpaths, on_options=args.on_options)
        return 0
