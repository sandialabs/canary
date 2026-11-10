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


def archive_only_help() -> str:
    lines = ["Which latest-result jobs to archive\n"]
    lines.extend(
        [
            "  all      - archive every job in the workspace",
            "\n  failed   - archive only jobs whose latest result failed",
            "\n  not_pass - archive jobs whose latest result is not PASS",
            "\n  passed   - archive only jobs whose latest result is PASS",
        ]
    )
    return "".join(lines)


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
            "--only",
            dest="only",
            choices=("all", "failed", "not_pass", "passed"),
            default="all",
            help=archive_only_help() + "\n\n  [default: all]",
        )
        parser.add_argument(
            "--exclude",
            action="append",
            default=None,
            metavar="PATTERN",
            help="Exclude archive members matching a shell-style pattern. May be given more than once.",
        )
        parser.add_argument(
            "dest",
            nargs="?",
            default=None,
            help="Archive file to create [default: <workspace-name>.tar.gz in the current directory]",
        )

    def execute(self, args: argparse.Namespace) -> int:
        workspace = app.open_workspace()
        dest = Path(args.dest) if args.dest else Path.cwd() / f"{workspace.root.name}.tar.gz"
        archive = app.archive_workspace(
            dest, only=getattr(args, "only", "all"), exclude=getattr(args, "exclude", None)
        )
        logger.info(f"[bold]Archived[/] workspace to {archive}")
        return 0
