# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import shutil
from typing import TYPE_CHECKING

import rich
import rich.console
import rich.table

from ...hookspec import hookimpl
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Info())


class Info(CanarySubcommand):
    name = "info"
    description = "Print information about test session"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument("-t", "--tag", help="Show information about this tag")

    def execute(self, args: argparse.Namespace) -> int:
        if args.tag:
            self.print_tag_info(args.tag)
        else:
            self.print_workspace_info()
        return 0

    def print_tag_info(self, tag: str) -> None:
        workspace = Workspace.load()
        fh = io.StringIO()
        fh.write(f"Tag: {tag}\n")
        selection = workspace.db.get_selection_metadata(tag)
        specs = [spec for spec in workspace.db.get_specs_by_tagname(tag) if not spec.mask]
        fh.write(f"Created on: {selection.created_on}\n")
        fh.write("Scan paths:\n")
        for root, paths in selection.scanpaths.items():
            fh.write(f"  {root}:\n")
            for path in paths:
                fh.write(f"    {path}\n")
        if selection.on_options:
            fh.write("Generation options:\n")
            for opt in selection.on_options:
                fh.write(f"  -o {opt}\n")
        if selection.keyword_exprs:
            fh.write("Keyword expressions:\n")
            for expr in selection.keyword_exprs:
                fh.write(f"  -k {expr}\n")
        if selection.parameter_expr:
            fh.write(f"Parameter expression:\n  -p {selection.parameter_expr}\n")
        if selection.owners:
            fh.write("Owners:\n")
            for o in selection.owners:
                fh.write(f"  --owner {o}\n")
        if selection.regex:
            fh.write(f"Regular expression filter:\n  --regex {selection.regex}\n")
        fh.write("Test specs:")
        table = rich.table.Table("No.", "ID", "Name")
        for i, spec in enumerate(specs):
            table.add_row(str(i), spec.id[:7], spec.display_name(resolve=True, style="rich"))
        console = rich.console.Console()
        groups = rich.console.Group(fh.getvalue(), table)
        if len(specs) > shutil.get_terminal_size().lines:
            with console.pager():
                console.print(groups)
        else:
            console.print(groups)

    def print_workspace_info(self) -> None:
        workspace = Workspace.load()
        info = workspace.info()
        fh = io.StringIO()
        fh.write(f"Workspace:   {info['root']}\n")
        fh.write(f"Version:     {info['version']}\n")
        fh.write(f"Sessions:    {info['session_count']}\n")
        fh.write(f"Latest:      {info['latest_session']}\n")
        fh.write(f"Tags:        {', '.join(info['tags'])}\n")
        rich.print(fh.getvalue())
