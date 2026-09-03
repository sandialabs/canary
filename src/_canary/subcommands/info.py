# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary info`` subcommand for printing workspace or tag summary information."""

import argparse
import io
import json
import shutil
import sys
from typing import TYPE_CHECKING

import rich
import rich.console
import rich.table
import yaml

from ..hookspec import hookimpl
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Info())


class Info(CanarySubcommand):
    """Print a summary of the current workspace or of a named tag, with optional JSON output."""

    name = "info"
    description = "Print information about test session"

    def setup_parser(self, parser: "Parser") -> None:
        """Register ``-t/--tag`` and ``--json`` arguments."""
        parser.add_argument("-t", "--tag", help="Show information about this tag")
        parser.add_argument(
            "--json",
            dest="output_json",
            action="store_true",
            default=False,
            help="Emit workspace information as JSON",
        )

    def execute(self, args: argparse.Namespace) -> int:
        """Dispatch to tag or workspace info printing (plain or JSON) and return 0."""
        if args.tag:
            if args.output_json:
                self.print_tag_info_json(args.tag)
            else:
                self.print_tag_info(args.tag)
        else:
            if args.output_json:
                self.print_workspace_info_json()
            else:
                self.print_workspace_info()
        return 0

    def print_tag_info_json(self, tag: str) -> None:
        """Emit JSON with spec count, creation date, and metadata for *tag* to stdout."""
        workspace = Workspace.load()
        specs = [spec for spec in workspace.db.load_specs_by_tagname(tag) if not spec.mask]
        selection = workspace.db.get_selection_metadata(tag)
        out = {
            "tag": tag,
            "created_on": selection.pop("created_on", None),
            "metadata": selection,
            "spec_count": len(specs),
            "specs": [{"id": spec.id, "name": spec.display_name(resolve=True)} for spec in specs],
        }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")

    def print_tag_info(self, tag: str) -> None:
        """Print a rich table of tag metadata and the specs it contains."""
        workspace = Workspace.load()
        fh = io.StringIO()
        fh.write(f"Tag: {tag}\n")
        specs = [spec for spec in workspace.db.load_specs_by_tagname(tag) if not spec.mask]
        selection = workspace.db.get_selection_metadata(tag)
        fh.write(f"Created on: {selection.pop('created_on')}\n")
        for key in list(selection.keys()):
            value = selection.pop(key)
            if value is not None:
                selection[key.replace("_", " ").title()] = value
        yaml.dump(selection, fh, default_flow_style=False)
        fh.write(f"Test specs ({len(specs)}):")
        table = rich.table.Table("No.", "ID", "Name")
        for i, spec in enumerate(specs):
            table.add_row(str(i), spec.id[:7], spec.display_name(resolve=True, style="rich"))
        console = rich.console.Console()
        groups = rich.console.Group(fh.getvalue(), table)
        use_pager = sys.stdout.isatty() and len(specs) > shutil.get_terminal_size().lines
        if use_pager:
            with console.pager():
                console.print(groups)
        else:
            console.print(groups)

    def print_workspace_info_json(self) -> None:
        """Emit JSON with root, version, spec count, test roots, sessions, and tags to stdout."""
        workspace = Workspace.load()
        info = workspace.info()
        unique_test_roots = sorted({spec.file_root.as_posix() for spec in info["specs"]})
        out = {
            "root": info["root"],
            "version": info["version"],
            "spec_count": len(info["specs"]),
            "test_roots": unique_test_roots,
            "session_count": info["session_count"],
            "latest_session": info["latest_session"],
            "tags": info["tags"],
        }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")

    def print_workspace_info(self) -> None:
        """Print a rich summary table of the current workspace."""
        workspace = Workspace.load()
        info = workspace.info()
        unique_test_roots = {spec.file_root.as_posix() for spec in info["specs"]}
        table = rich.table.Table(show_header=False)
        table.add_row("Workspace", info["root"])
        table.add_row("Version", info["version"])
        table.add_row("Specs", str(len(info["specs"])))
        table.add_row("Test roots", ", ".join(unique_test_roots))
        table.add_row("Sessions", str(info["session_count"]))
        table.add_row("Latest", info["latest_session"])
        table.add_row("Tags", ", ".join(info["tags"]))
        rich.print(table)
