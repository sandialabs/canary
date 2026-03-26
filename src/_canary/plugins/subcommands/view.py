# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...hookspec import hookimpl
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(View())


class View(CanarySubcommand):
    name = "view"
    description = "Manage a workspace's view"

    def setup_parser(self, parser: "Parser") -> None:
        sp = parser.add_subparsers(dest="view_subcommand")
        sp.add_parser("refresh", help="Refresh the view")

    def execute(self, args: argparse.Namespace) -> int:
        if args.view_subcommand == "refresh":
            workspace = Workspace.load()
            workspace.rebuild_view()
        return 0
