# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...hookspec import hookimpl
from ...view import ViewSettings
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
        p = sp.add_parser("refresh", help="Refresh the view", aliases=["create"])
        p.add_argument(
            "--mode",
            default="symlink",
            choices=("symlink", "hardlink", "copy"),
            help="View mode [default: %(default)s]",
        )
        p.add_argument(
            "--only",
            default="all",
            choices=("all", "failed", "not_pass", "passed"),
            help="Which tests to include [default: %(default)s]",
        )
        p.add_argument(
            "--name",
            default="TestResults",
            help="View name [default: %(default)s]",
        )

    def execute(self, args: argparse.Namespace) -> int:
        if args.view_subcommand in ("refresh", "create"):
            view_t = ViewSettings(when="always", only=args.only, mode=args.mode, name=args.name)
            workspace = Workspace.load()
            workspace.rebuild_view(view_t=view_t)
        return 0
