# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...util import logging
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common.pathspec import PathSpec

if TYPE_CHECKING:
    from ...config.argparsing import Parser


logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Add())


class Add(CanarySubcommand):
    name = "add"
    description = "Add test generators to Canary session"

    def setup_parser(self, parser: "Parser"):
        PathSpec.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        workspace.add(args.paths, pedantic=True)
        return 0
