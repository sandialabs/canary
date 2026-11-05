# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from .. import app
from ..plugins.hookspec import hookimpl
from ..util import logging
from .base import CanarySubcommand

logger = logging.get_logger(__name__)

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Archive())


class Archive(CanarySubcommand):
    name = "archive"
    description = "Archive the current Canary workspace"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "dest",
            nargs="?",
            default=None,
            help="Archive file to create [default: <workspace-name>.tar.gz in the current directory]",
        )

    def execute(self, args: argparse.Namespace) -> int:
        workspace = app.open_workspace()
        dest = Path(args.dest) if args.dest else Path.cwd() / f"{workspace.root.name}.tar.gz"
        archive = app.archive_workspace(dest)
        logger.info(f"[bold]Archived[/] workspace to {archive}")
        return 0
