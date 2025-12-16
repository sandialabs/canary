# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import shutil
from typing import TYPE_CHECKING

import rich
import rich.console

from ...hookspec import hookimpl
from ...rules import Rule
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
        selector = workspace.get_selector(tag)
        specs = [spec for spec in workspace.get_selection(tag) if not spec.mask]
        fh.write(f"Selected on: {selector.created_on}\n")
        fh.write("Selection filters:\n")
        n = 2
        for rule in selector.rules:
            n += 1
            fh.write(f"  • {Rule.reconstruct(rule)}\n")
        fh.write(f"Test specs (n = {len(specs)}):\n")
        for spec in specs:
            n += 1
            fh.write(f"  • {spec.id[:7]}: {spec.display_name(resolve=True)}\n")
        console = rich.console.Console()
        if n > shutil.get_terminal_size().lines:
            with console.pager():
                console.print(fh.getvalue())
        else:
            console.print(fh.getvalue())

    def print_workspace_info(self) -> None:
        workspace = Workspace.load()
        info = workspace.info()
        fh = io.StringIO()
        fh.write(f"Workspace:   {info['root']}\n")
        fh.write(f"Version:     {info['version']}\n")
        fh.write(f"Generators:  {info['generator_count']}\n")
        fh.write(f"Sessions:    {info['session_count']}\n")
        fh.write(f"Latest:      {info['latest_session']}\n")
        fh.write(f"Tags:        {', '.join(info['tags'])}\n")
        rich.print(fh.getvalue())
