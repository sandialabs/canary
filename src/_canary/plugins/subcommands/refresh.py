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
    parser.add_command(Refresh())


class Refresh(CanarySubcommand):
    name = "refresh"
    description = "Refresh the workspace's view"

    def execute(self, args: argparse.Namespace) -> int:
        workspace = Workspace.load()
        workspace.rebuild_view()
        return 0
