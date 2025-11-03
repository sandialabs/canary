# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...repo import Repo
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(GarbageCollect())


class GarbageCollect(CanarySubcommand):
    name = "gc"
    description = "Remove working directories of test cases having status 'success'"

    def execute(self, args: argparse.Namespace) -> int:
        repo = Repo()
        repo.gc()
