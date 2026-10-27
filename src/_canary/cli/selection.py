# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from .. import app
from ..generation.collect import Collector
from ..generation.generate import Generator
from ..plugins.hookspec import hookimpl
from ..select import Selector
from ..util import logging
from .base import CanarySubcommand
from .run import ScanPathSpec

if TYPE_CHECKING:
    from ..config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Selection())


class Selection(CanarySubcommand):
    name = "selection"
    description = "Create selections of tests to run"
    add_help = False

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="select_command", required=True)
        p = subparsers.add_parser("create")
        Collector.setup_parser(p)
        Generator.setup_parser(p)
        Selector.setup_parser(p)
        p.add_argument(
            "runpaths",
            action=ScanPathSpec,
            nargs=argparse.REMAINDER,
            metavar="pathspec [--] [user args...]",
            help="Filesystem paths to search, using the same pathspec syntax as canary run",
        )
        p = subparsers.add_parser("rm")
        p.add_argument("tag", help="Remove this selection")
        p = subparsers.add_parser("rename")
        p.add_argument("old", help="Current tag name")
        p.add_argument("new", help="New tag name")

    def execute(self, args: "argparse.Namespace") -> int:
        if args.select_command == "create":
            if app.is_selection(args.tag):
                raise ValueError(
                    logging.colorize(
                        f"Selection {args.tag!r} already exists, run "
                        f"[bold]canary selection refresh {args.tag}[/] to regnerate specs"
                    )
                )
            if getattr(args, "request", None) is not None:
                args.scanpaths = args.request.value
            if not args.scanpaths:
                raise ValueError("No paths to search")
            app.open_workspace().create_selection(
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
            app.delete_selection(args.tag)
        elif args.select_command == "rename":
            app.rename_selection(args.old, args.new)
        else:
            raise ValueError(f"Unknown command canary selection {args.select_command}")
        return 0
