# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

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
    parser.add_command(Select())


class Select(CanarySubcommand):
    name = "select"
    description = "Create tagged selection of tests"

    def setup_parser(self, parser: "Parser") -> None:
        group = parser.get_group("test spec selection")
        group.add_argument(
            "-r",
            "--from-root",
            dest="from_root",
            metavar="root",
            action="append",
            help="Restrict selection to tests whose source files are located under root"
        )
        group.add_argument(
            "-d", "--delete", dest="delete_tag", action="store_true", help="Delete tag"
        )
        group.add_argument(
            "-m", "--move", dest="move_tag", metavar="oldtag", help="Move/rename oldtag to tag"
        )
        group.add_argument(
            "-f", "--from", dest="from_tag", metavar="tag", help="Create selection from tag"
        )
        Selector.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        if args.delete_tag:
            workspace.db.delete_selection(args.tag)
        elif args.move_tag:
            workspace.db.rename_selection(args.move_tag, args.tag)
        elif args.from_tag:
            resolved = workspace.db.load_specs_by_tagname(args.from_tag)
            specs = workspace.select_from_specs(
                resolved,
                prefixes=args.from_root,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
            workspace.db.put_selection(
                args.tag,
                specs,
                prefixes=args.from_root,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
        else:
            if workspace.is_tag(args.tag):
                raise ValueError(logging.colorize(f"Selection {args.tag!r} already exists"))
            workspace.select(
                args.tag,
                prefixes=args.from_root,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
            logger.info(f"To run this selection execute '[bold]canary run {args.tag}[/]'")
        return 0
