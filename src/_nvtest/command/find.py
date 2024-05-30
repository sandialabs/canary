import argparse
import os
from typing import TYPE_CHECKING

from ..finder import Finder
from ..session import Session
from ..util import logging
from .common import add_mark_arguments
from .common import add_resource_arguments

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser


description = "Search paths for test files"


def setup_parser(parser: "Parser"):
    add_mark_arguments(parser)
    group = parser.add_argument_group("console reporting")
    group.add_argument(
        "--no-header",
        action="store_true",
        default=False,
        help="Disable header [default: %(default)s]",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--paths",
        dest="paths",
        action="store_true",
        default=False,
        help="Print file paths, grouped by root",
    )
    group.add_argument(
        "-f",
        "--files",
        dest="files",
        action="store_true",
        default=False,
        help="Print file paths",
    )
    group.add_argument(
        "-g",
        dest="graph",
        action="store_true",
        default=False,
        help="Print DAG of test cases",
    )
    group.add_argument(
        "--keywords",
        action="store_true",
        default=False,
        help="Show available keywords",
    )
    parser.add_argument(
        "--owner", dest="owners", action="append", help="Show tests owned by 'owner'"
    )
    add_resource_arguments(parser)
    parser.add_argument("search_paths", nargs="*", help="Search path[s]")


def find(args: "argparse.Namespace") -> int:
    finder = Finder()
    search_paths = args.search_paths or [os.getcwd()]
    for path in search_paths:
        finder.add(path)
    finder.prepare()
    generators = finder.discover()
    cases = Finder.freeze(
        generators,
        rh=args.rh,
        keyword_expr=args.keyword_expr,
        parameter_expr=args.parameter_expr,
        on_options=args.on_options,
        owners=None if not args.owners else set(args.owners),
    )
    values = ("ready", "created", "pending")
    cases_to_run = sorted([c for c in cases if c.status.value in values], key=lambda x: x.name)
    if not args.files and not args.no_header:
        logging.emit(Session.overview(cases))
    if args.keywords:
        Finder.pprint_keywords(cases_to_run)
    elif args.paths:
        Finder.pprint_paths(cases_to_run)
    elif args.files:
        Finder.pprint_files(cases_to_run)
    elif args.graph:
        Finder.pprint_graph(cases_to_run)
    else:
        Finder.pprint(cases_to_run)
    return 0
