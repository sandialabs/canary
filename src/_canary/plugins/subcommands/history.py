# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
from typing import TYPE_CHECKING

from ...hookspec import hookimpl
from ...third_party import colify
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
        results = workspace.db.get_single_result(args.id)
        table: list[list[str]] = []
        header = ["Session", "Exit Code", "Duration", "Status", "Details"]
        widths: list[int] = [len(_) for _ in header]
        for entry in results:
            row: list[str] = []
            row.append(entry["session"])
            row.append(str(entry["status"]["code"]))
            row.append(str(entry["timekeeper"]["duration"]))
            row.append(str(entry["status"]["category"]))
            row.append(str(entry["status"]["reason"]))
            widths = [max(widths[i], len(row[i])) for i in range(len(header))]
            table.append(row)
        hlines: list[str] = ["=" * width for width in widths]
        table.insert(0, header)
        table.insert(1, hlines)
        fh = io.StringIO()
        colify.colify_table(table, output=fh)
        print(fh.getvalue().strip())
        return 0
