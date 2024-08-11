import argparse
import os
from typing import TYPE_CHECKING

from ..finder import Finder
from ..session import Session
from ..util import logging
from ..util.banner import banner
from .common import PathSpec
from .common import add_mark_arguments
from .common import add_resource_arguments

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser


description = "Search paths for test files"


def _add_group_argument(group, name, help_string, add_short_arg=True):
    args = [f"--{name}"]
    if add_short_arg:
        args.insert(0, f"-{name[0]}")
    kwargs = dict(dest=f"print_{name}", action="store_true", default=False, help=help_string)
    group.add_argument(*args, **kwargs)


def setup_parser(parser: "Parser"):
    group = parser.add_mutually_exclusive_group()
    _add_group_argument(group, "paths", "Print file paths, grouped by root", False)
    _add_group_argument(group, "files", "Print file paths")
    _add_group_argument(group, "graph", "Print DAG of test cases")
    _add_group_argument(group, "keywords", "Show available keywords", False)
    parser.add_argument(
        "--owner", dest="owners", action="append", help="Show tests owned by 'owner'"
    )
    add_mark_arguments(parser)
    add_resource_arguments(parser)
    parser.add_argument(
        "pathspec",
        metavar="pathspec",
        nargs="*",
        help="Test file[s] or directories to search",
    )


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
    if not args.print_files:
        logging.emit(Session.overview(cases))
    if args.print_keywords:
        Finder.pprint_keywords(cases_to_run)
    elif args.print_paths:
        Finder.pprint_paths(cases_to_run)
    elif args.print_files:
        Finder.pprint_files(cases_to_run)
    elif args.print_graph:
        Finder.pprint_graph(cases_to_run)
    else:
        Finder.pprint(cases_to_run)
    return 0
