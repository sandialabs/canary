# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
from typing import TYPE_CHECKING

from ...generate import Generator
from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...generate import Generator

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Generate())


class Generate(CanarySubcommand):
    name = "generate"
    description = "Generate test specs"

    def setup_parser(self, parser: "Parser") -> None:
        Generator.setup_parser(parser)

    def execute(self, args: argparse.Namespace) -> int:
        workspace = Workspace.load()
        workspace.generate_testspecs(on_options=args.on_options)
        return 0
