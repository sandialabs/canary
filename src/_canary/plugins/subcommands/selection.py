# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...collect import Collector
from ...generate import Generator
from ...hookspec import hookimpl
from ...select import Selector
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Selection())


class Selection(CanarySubcommand):
    name = "selection"
    description = "Create selections of tests to run"

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="select_command")
        p = subparsers.add_parser("create")
        Collector.setup_parser(p)
        Generator.setup_parser(p)
        Selector.setup_parser(p)
        p = subparsers.add_parser("rm")
        p.add_argument("tag", help="Remove this selection")
        p = subparsers.add_parser("rename")
        p.add_argument("old", help="Current tag name")
        p.add_argument("new", help="New tag name")

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        if args.select_command == "create":
            if workspace.is_tag(args.tag):
                raise ValueError(
                    logging.colorize(
                        f"Selection {args.tag!r} already exists, run "
                        f"[bold]canary selection refresh {args.tag}[/] to regnerate specs"
                    )
                )
            if not args.scanpaths:
                raise ValueError("No paths to search")
            workspace.create_selection(
                args.tag,
                args.scanpaths,
                on_options=args.on_options,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
            logger.info(f"To run this selection execute '[bold]canary run {args.tag}[/]'")
        elif args.select_command == "rm":
            workspace.db.delete_selection(args.tag)
        elif args.select_command == "rename":
            workspace.db.rename_selection(args.old, args.new)
        else:
            raise ValueError(f"Unknown command canary selection {args.select_command}")
        return 0
