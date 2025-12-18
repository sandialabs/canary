# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

import rich
from rich.table import Table

from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(History())


class History(CanarySubcommand):
    name = "history"
    description = "Print status history for a test"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument("id", help="Show history for this test case")

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        results = workspace.db.get_result_history(args.id)
        table = Table(expand=False)
        for col in ["Name", "ID", "Session", "Exit Code", "Duration", "Status", "Details"]:
            table.add_column(col)
        for entry in results:
            row: list[str] = []
            row.append(entry["spec_name"])
            row.append(entry["id"][:7])
            row.append(entry["session"])
            row.append(str(entry["status"].code))
            row.append(str(entry["timekeeper"].duration))
            row.append(str(entry["status"].display_name(style="rich")))
            row.append(str(entry["status"].reason))
            table.add_row(*row)
        rich.print(table)
        return 0
