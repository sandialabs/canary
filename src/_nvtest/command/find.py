import argparse
import os
from typing import TYPE_CHECKING

from ..finder import Finder
from ..session import Session
from ..util import logging
from ..util.banner import banner
from .common import PathSpec

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser


description = "Search paths for test files"


def setup_parser(parser: "Parser"):
    from .run import setup_parser as setup_run_parser

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
    setup_run_parser(parser)


def parse_search_paths(args: argparse.Namespace) -> dict[str, list[str]]:
    PathSpec.parse(args)
    parsed: dict[str, list[str]] = {}
    if isinstance(args.paths, list):
        args.paths = {path: [] for path in args.paths}
    errors = 0
    for root, paths in args.paths.items():
        if not root:
            root = os.getcwd()
        if not os.path.isdir(root):
            errors += 1
            logging.warning(f"{root}: directory does not exist and will not be searched")
        else:
            root = os.path.abspath(root)
            parsed[root] = paths
    if errors:
        logging.warning("one or more search paths does not exist")
    return parsed


def find(args: argparse.Namespace) -> int:
    logging.emit(banner() + "\n")
    search_paths = parse_search_paths(args)
    finder = Finder()
    for root, paths in search_paths.items():
        finder.add(root, *paths, tolerant=True)
    finder.prepare()
    generators = finder.discover()
    cases = Finder.freeze(
        generators,
        rh=args.rh,
        keyword_expr=args.keyword_expr,
        parameter_expr=args.parameter_expr,
        on_options=args.on_options,
        owners=None if not args.owners else set(args.owners),
        env_mods=args.env_mods.get("test") or {},
    )
    cases_to_run = [case for case in cases if not case.mask]
    cases_to_run.sort(key=lambda x: x.name)
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
