# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ... import config
from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

logger = logging.get_logger(__name__)

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Init())


@hookimpl(trylast=True)
def canary_initfinish(workspace: Workspace) -> None:
    logger.info(f"[bold]Finished[/] initializing canary workspace at {workspace.root.parent}")


class Init(CanarySubcommand):
    name = "init"
    description = "Initialize a Canary session"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument("-w", action="store_true", help="Wipe any existing session first")
        parser.add_argument(
            "path",
            default=os.getcwd(),
            nargs="?",
            help="Initialize session in this directory [default: %(default)s]",
        )
        parser.add_argument(
            "-n,--no-post-actions",
            action="store_false",
            dest="post_actions",
            help="Do not run post-initialization actions on the workspace",
        )
        parser.set_defaults(post_actions=True)

    def execute(self, args: "argparse.Namespace") -> int:
        ws = Workspace.create(Path(args.path).absolute(), force=args.w)
        if args.post_actions:
            config.pluginmanager.hook.canary_initfinish(workspace=ws)
        return 0
