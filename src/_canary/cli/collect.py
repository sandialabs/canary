# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary collect`` subcommand for finding and generating test cases."""

import argparse
from typing import TYPE_CHECKING

from .. import app
from ..generation.collect import Collector
from ..generation.generate import Generator
from ..plugins.hookspec import hookimpl
from ..util import logging
from .base import CanarySubcommand
from .run import ScanPathSpec

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
        parser.add_argument(
            "runpaths",
            action=ScanPathSpec,
            nargs=argparse.REMAINDER,
            metavar="pathspec [--] [user args...]",
            help="Filesystem paths to collect, using the same pathspec syntax as canary run",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        """Collect test cases from ``args.scanpaths`` into the current workspace."""
        if getattr(args, "request", None) is not None:
            args.scanpaths = args.request.value
        app.collect(args.scanpaths, on_options=args.on_options)
        return 0
