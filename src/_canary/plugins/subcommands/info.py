# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
from typing import TYPE_CHECKING

from ...rules import Rule

from ...hookspec import hookimpl
from ...util import logging
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
        text: str
        if args.tag:
            text = self.get_tag_info(args.tag)
        else:
            text = self.get_workspace_info()
        logging.pager(text)
        return 0

    def get_tag_info(self, tag: str) -> str:
        workspace = Workspace.load()
        fh = io.StringIO()
        fh.write(f"Tag: {tag}\n")
        selector = workspace.get_selector(tag)
        specs = [spec for spec in workspace.get_selection(tag) if not spec.mask]
        fh.write(f"Selected on: {selector.created_on}\n")
        fh.write("Selection filters:\n")
        for rule in selector.rules:
            fh.write(f"  • {Rule.reconstruct(rule)}\n")
        fh.write(f"Test specs (n = {len(specs)}):\n")
        for spec in specs:
            name = spec.file_path.parent / spec.pretty_name
            fh.write(f"  • {spec.id[:7]}: {name}\n")
        return fh.getvalue()

    def get_workspace_info(self) -> str:
        workspace = Workspace.load()
        info = workspace.info()
        fh = io.StringIO()
        fh.write(f"Workspace:   {info['root']}\n")
        fh.write(f"Version:     {info['version']}\n")
        fh.write(f"Generators:  {info['generator_count']}\n")
        fh.write(f"Sessions:    {info['session_count']}\n")
        fh.write(f"Latest:      {info['latest_session']}\n")
        fh.write(f"Tags:        {', '.join(info['tags'])}\n")
        return fh.getvalue()
