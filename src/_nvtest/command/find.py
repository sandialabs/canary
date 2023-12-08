import os
import sys
from typing import TYPE_CHECKING

from .. import config
from ..finder import Finder
from ..util import graph
from ..util import tty
from ..util.time import hhmmss
from ..util.tty.colify import colified
from ..util.tty.color import colorize
from .common import add_mark_arguments

if TYPE_CHECKING:
    import argparse

    from _nvtest.config.argparsing import Parser
    from _nvtest.test.testcase import TestCase


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
    parser.add_argument("search_paths", nargs="*", help="Search path[s]")


def find(args: "argparse.Namespace") -> int:
    if not args.no_header:
        print_front_matter()
    finder = Finder()
    search_paths = args.search_paths or [os.getcwd()]
    for path in search_paths:
        finder.add(path)
    finder.prepare()
    tree = finder.populate()
    cases = Finder.freeze(
        tree,
        cpu_count=config.get("machine:cpu_count"),
        keyword_expr=args.keyword_expr,
        parameter_expr=args.parameter_expr,
        on_options=args.on_options,
    )
    cases_to_run = [case for case in cases if case.status == "pending"]
    if not args.no_header:
        print_testcase_summary(args, cases)
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
    _, max_width = tty.terminal_size()
    for root, paths in unique_files.items():
        label = colorize("@m{%s}" % root)
        tty.hline(label, max_width=max_width)
        cols = colified(sorted(paths), indent=2, width=max_width)
        tty.emit(cols + "\n")


def _print_files(cases_to_run: "list[TestCase]"):
    unique_files: set[str] = set()
    for case in cases_to_run:
        unique_files.add(case.file)
    for file in sorted(unique_files):
        tty.emit(file + "\n")


def _print_keywords(cases_to_run: "list[TestCase]"):
    unique_kwds: dict[str, set[str]] = dict()
    for case in cases_to_run:
        unique_kwds.setdefault(case.file_root, set()).update(case.keywords())
    _, max_width = tty.terminal_size()
    for root, kwds in unique_kwds.items():
        label = colorize("@m{%s}" % root)
        tty.hline(label, max_width=max_width)
        cols = colified(sorted(kwds), indent=2, width=max_width)
        tty.emit(cols + "\n")


def _print_graph(cases_to_run: "list[TestCase]"):
    graph.print(cases_to_run, file=sys.stdout)


def _print(cases_to_run: "list[TestCase]"):
    _, max_width = tty.terminal_size()
    tree: dict[str, list[str]] = {}
    for case in cases_to_run:
        line = f"{hhmmss(case.runtime)}    {case.name}"
        tree.setdefault(case.file_root, []).append(line)
    for root, lines in tree.items():
        cols = colified(lines, indent=2, width=max_width)
        label = colorize("@m{%s}" % root)
        tty.hline(label, max_width=max_width)
        tty.emit(cols + "\n")
        summary = f"found {len(lines)} test cases\n"
        tty.emit(summary)


def print_front_matter():
    n = N = config.get("machine:cpu_count")
    p = config.get("system:platform")
    v = config.get("python:version")
    print(f"platform {p} -- Python {v}, num cores: {n}, max cores: {N}")
    print(f"rootdir: {os.getcwd()}")


def print_testcase_summary(args: "argparse.Namespace", cases: "list[TestCase]") -> None:
    files = {case.file for case in cases}
    t = "@*{collected %d tests from %d files}" % (len(cases), len(files))
    print(colorize(t))
    cases_to_run = [case for case in cases if case.status == "pending"]
    max_workers = getattr(args, "max_workers", None)
    max_workers = max_workers or config.get("machine:cpu_count")
    files = {case.file for case in cases_to_run}
    fmt = "@*g{running} %d test cases from %d files with %s workers"
    print(colorize(fmt % (len(cases_to_run), len(files), max_workers)))
    excluded = [case for case in cases if case.excluded]
    excluded_reasons: dict[str, int] = {}
    for case in excluded:
        assert case.status.details is not None
        reason = case.status.details
        excluded_reasons[reason] = excluded_reasons.get(reason, 0) + 1
    print(colorize("@*b{skipping} %d test cases" % len(excluded)))
    reasons = sorted(excluded_reasons, key=lambda x: excluded_reasons[x])
    for reason in reversed(reasons):
        print(f"  • {excluded_reasons[reason]} {reason.lstrip()}")
    return
