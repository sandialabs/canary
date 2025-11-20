# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import TextIO

from ... import config
from ...error import StopExecution
from ...generator import AbstractTestGenerator
from ...testspec import finalize
from ...third_party.colify import colified
from ...third_party.color import colorize
from ...util import graph
from ...util import logging
from ...util.json_helper import json
from ...util.term import terminal_size
from ...util.time import hhmmss
from ...workspace import generate_specs
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from ..types import ScanPath
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...generator import AbstractTestGenerator
    from ...testspec import TestSpec

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Find())


class Find(CanarySubcommand):
    name = "find"
    description = "Search paths for test files"
    epilog = "See canary help --pathspec for help on the path specification"

    def setup_parser(self, parser: "Parser") -> None:
        group = parser.add_mutually_exclusive_group()
        add_group_argument(group, "paths", "Print file paths, grouped by root", False)
        add_group_argument(group, "files", "Print file paths", False)
        add_group_argument(group, "graph", "Print DAG of test specs")
        add_group_argument(group, "lock", "Dump test specs to lock file")
        parser.add_argument(
            "--owner", dest="owners", action="append", help="Show tests owned by 'owner'"
        )
        add_filter_arguments(parser)
        add_resource_arguments(parser)
        PathSpec.setup_parser(parser)

    def execute(self, args: argparse.Namespace) -> int:
        generators: list["AbstractTestGenerator"] = []
        hook = config.pluginmanager.hook.canary_collect_generators
        for root, paths in args.paths.items():
            p = ScanPath(root=root, paths=paths)
            generators.extend(hook(scan_path=p))
        specs = generate_specs(generators=generators, on_options=args.on_options)

        config.pluginmanager.hook.canary_testsuite_mask(
            specs=specs,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            owners=None if not args.owners else set(args.owners),
            regex=args.regex_filter,
            ids=None,
        )
        quiet = bool(args.print_files)
        specs_to_run = [spec for spec in specs if not spec.mask]
        if not specs_to_run:
            raise StopExecution("No tests to run", 7)
        final = finalize(specs)
        config.pluginmanager.hook.canary_collectreport(specs=final)
        specs_to_run.sort(key=lambda x: x.name)
        if args.print_paths:
            pprint_paths(specs_to_run)
        elif args.print_files:
            pprint_files(specs_to_run)
        elif args.print_graph:
            pprint_graph(specs_to_run)
        elif args.print_lock:
            file = Path(config.invocation_dir) / "testspecs.lock"
            states = [spec.asdict() for spec in specs_to_run]
            file.write_text(json.dumps({"testspecs": states}, indent=2))
            logger.info("test specs written to testspec.lock")
        else:
            pprint(specs_to_run)
        return 0


def add_group_argument(group, name, help_string, add_short_arg=True):
    args = [f"--{name}"]
    if add_short_arg:
        args.insert(0, f"-{name[0]}")
    kwargs = dict(dest=f"print_{name}", action="store_true", default=False, help=help_string)
    group.add_argument(*args, **kwargs)


def pprint_paths(specs: list["TestSpec"], file: TextIO = sys.stdout) -> None:
    unique_generators: dict[str, set[str]] = dict()
    for spec in specs:
        unique_generators.setdefault(spec.file_root, set()).add(spec.file_path)
    _, max_width = terminal_size()
    for root, paths in unique_generators.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        cols = colified(sorted(paths), indent=2, width=max_width)
        file.write(cols + "\n")


def pprint_files(specs: list["TestSpec"], file: TextIO = sys.stdout) -> None:
    for f in sorted(set([spec.file for spec in specs])):
        file.write("%s\n" % os.path.relpath(f, os.getcwd()))


def pprint_keywords(specs: list["TestSpec"], file: TextIO = sys.stdout) -> None:
    unique_kwds: dict[str, set[str]] = dict()
    for spec in specs:
        unique_kwds.setdefault(spec.file_root, set()).update(spec.keywords)
    _, max_width = terminal_size()
    for root, kwds in unique_kwds.items():
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        cols = colified(sorted(kwds), indent=2, width=max_width)
        file.write(cols + "\n")


def pprint_graph(specs: list["TestSpec"], file: TextIO = sys.stdout) -> None:
    graph.print(specs, file=file)


def pprint(specs: list["TestSpec"], file: TextIO = sys.stdout) -> None:
    _, max_width = terminal_size()
    tree: dict[str, list[str]] = {}
    for spec in specs:
        line = f"{hhmmss(spec.timeout):11s}    {spec.fullname}"
        tree.setdefault(spec.file_root, []).append(line)
    for root, lines in tree.items():
        cols = colified(lines, indent=2, width=max_width)
        label = colorize("@m{%s}" % root)
        logging.hline(label, max_width=max_width, file=file)
        file.write(cols + "\n")
