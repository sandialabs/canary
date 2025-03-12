import argparse
import os
from typing import TYPE_CHECKING

from ...util import logging
from ...util.banner import banner
from ...util.filesystem import find_work_tree
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Rebaseline()


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    aliases = ["baseline"]
    description = "Rebaseline tests"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser)
        parser.add_argument("-f", dest="f_pathspec", help=argparse.SUPPRESS)
        parser.add_argument(
            "pathspec",
            metavar="pathspec",
            nargs="*",
            help="Test file[s] or directories to search",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        from ...session import Session

        work_tree = find_work_tree(os.getcwd())
        if work_tree is None:
            raise ValueError("rebaseline must be executed in a canary work tree")
        logging.emit(banner() + "\n")
        PathSpec.parse(args)
        session = Session(args.work_tree, mode="r")
        session.filter(
            start=args.start,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            case_specs=getattr(args, "case_specs", None),
        )
        for case in session.active_cases():
            case.do_baseline()
        return 0
