# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary collect`` subcommand for finding and generating test cases."""

import argparse
from typing import TYPE_CHECKING

from ..collect import Collector
from ..generate import Generator
from ..hookspec import hookimpl
from ..util import logging
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Collect())


class Collect(CanarySubcommand):
    """Scan paths for test generators, expand parametrized test cases, and store them in the workspace."""

    name = "collect"
    description = "Find and generate test cases"

    def setup_parser(self, parser: "Parser") -> None:
        """Register scan-path and generator option arguments."""
        Collector.setup_parser(parser)
        Generator.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        """Collect test cases from ``args.scanpaths`` into the current workspace."""
        workspace = Workspace.load()
        workspace.collect(args.scanpaths, on_options=args.on_options)
        return 0
