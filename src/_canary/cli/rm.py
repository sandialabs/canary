# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ..plugins.hookspec import hookimpl
from ..session.workspace import Workspace
from ..util import logging
from .base import CanarySubcommand

logger = logging.get_logger(__name__)

if TYPE_CHECKING:
    from ..config.argparsing import Parser


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
            nargs="?",
            default=None,
            help="Remove the workspace located at PATH (the directory containing .canary, "
            "or the .canary directory itself) [default: .].  Parent directories are "
            "never searched.",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        path = Path(args.rm_path) if args.rm_path else Path(os.getcwd())
        if not path.exists():
            logger.error(f"{path}: no such file or directory")
            return 1
        if p := Workspace.detach(start=path, cleanup_stale=True):
            logger.info(f"[bold]Removed[/] workspace at {p}")
        return 0
