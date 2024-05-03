import argparse
import os
import sys
from typing import TYPE_CHECKING

from ..finder import Finder
from ..session import Session
from ..third_party.colify import colified
from ..third_party.color import colorize
from ..util import graph
from ..util import logging
from ..util.term import terminal_size
from ..util.time import hhmmss
from .common import add_mark_arguments
from .common import add_resource_arguments

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser
    from _nvtest.test.case import TestCase


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
    files = finder.discover()
    cases = Finder.freeze(
        files,
        resourceinfo=args.resourceinfo,
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
        _print_keywords(cases_to_run)
    elif args.paths:
        _print_paths(cases_to_run)
    elif args.files:
        _print_files(cases_to_run)
    elif args.graph:
        _print_graph(cases_to_run)
    else:
        _print(cases_to_run)
    return 0


def _print_paths(cases_to_run: "list[TestCase]"):
    unique_files: dict[str, set[str]] = dict()
    for case in cases_to_run:
        unique_files.setdefault(case.file_root, set()).add(case.file_path)
    _, max_width = terminal_size()
    for root, paths in unique_files.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width)
        cols = colified(sorted(paths), indent=2, width=max_width)
        logging.emit(cols + "\n")


def _print_files(cases_to_run: "list[TestCase]"):
    for file in sorted(set([case.file for case in cases_to_run])):
        logging.emit(os.path.relpath(file, os.getcwd()) + "\n")


def _print_keywords(cases_to_run: "list[TestCase]"):
    unique_kwds: dict[str, set[str]] = dict()
    for case in cases_to_run:
        unique_kwds.setdefault(case.file_root, set()).update(case.keywords())
    _, max_width = terminal_size()
    for root, kwds in unique_kwds.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width)
        cols = colified(sorted(kwds), indent=2, width=max_width)
        logging.emit(cols + "\n")


def _print_graph(cases_to_run: "list[TestCase]"):
    graph.print(cases_to_run, file=sys.stdout)


def _print(cases_to_run: "list[TestCase]"):
    _, max_width = terminal_size()
    tree: dict[str, list[str]] = {}
    for case in cases_to_run:
        line = f"{hhmmss(case.runtime)}    {case.name}"
        tree.setdefault(case.file_root, []).append(line)
    for root, lines in tree.items():
        cols = colified(lines, indent=2, width=max_width)
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width)
        logging.emit(cols + "\n")
        logging.emit(f"found {len(lines)} test cases\n")
