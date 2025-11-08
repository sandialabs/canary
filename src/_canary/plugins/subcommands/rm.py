# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ...util import logging
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

logger = logging.get_logger(__name__)

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(RemoveWorkspace())


class RemoveWorkspace(CanarySubcommand):
    name = "rm"
    description = "Remove Canary workspace"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument(
            "rm_path",
            metavar="PATH",
            default=os.getcwd(),
            help="Remove workspace at PATH",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        if p := Workspace.remove(start=Path(args.rm_path)):
            logger.info(f"Removed canary workspace from {p}")
        return 0
