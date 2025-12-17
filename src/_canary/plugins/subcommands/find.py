# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import io
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import rich
import rich.console
from rich.columns import Columns
from rich.rule import Rule

from ... import config
from ... import rules
from ...collect import Collector
from ...error import StopExecution
from ...generate import Generator
from ...hookspec import hookimpl
from ...select import Selector
from ...util import graph
from ...util import logging
from ...util.json_helper import json
from ..types import CanarySubcommand
from .common import add_resource_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testspec import ResolvedSpec

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
        add_group_argument(group, "keywords", "Print keywords by root", False)
        Collector.setup_parser(parser)
        Generator.setup_parser(parser)
        Selector.setup_parser(parser, tagged="none")
        add_resource_arguments(parser)

    def execute(self, args: argparse.Namespace) -> int:
        collector = Collector()
        collector.add_scanpaths(args.scanpaths)
        generators = collector.run()

        generator = Generator(generators, workspace=Path.cwd(), on_options=args.on_options or [])
        resolved = generator.run()

        selector = Selector(resolved, Path.cwd())
        if args.keyword_exprs:
            selector.add_rule(rules.KeywordRule(args.keyword_exprs))
        if args.parameter_expr:
            selector.add_rule(rules.ParameterRule(args.parameter_expr))
        if args.owners:
            selector.add_rule(rules.OwnersRule(args.owners))
        if args.regex_filter:
            selector.add_rule(rules.RegexRule(args.regex_filter))
        selector.run()

        final = [spec for spec in resolved if not spec.mask]
        if not final:
            raise StopExecution("No tests to run", 7)
        final.sort(key=lambda x: x.name)
        if args.print_paths:
            pprint_paths(final)
        elif args.print_files:
            pprint_files(final)
        elif args.print_graph:
            pprint_graph(final)
        elif args.print_keywords:
            pprint_keywords(final)
        elif args.print_lock:
            file = Path(config.invocation_dir) / "testspecs.lock"
            states = [spec.asdict() for spec in final]
            file.write_text(json.dumps({"testspecs": states}, indent=2))
            logger.info("test specs written to testspec.lock")
        else:
            pprint(final)
        return 0


def add_group_argument(group, name, help_string, add_short_arg=True):
    args = [f"--{name}"]
    if add_short_arg:
        args.insert(0, f"-{name[0]}")
    kwargs = dict(dest=f"print_{name}", action="store_true", default=False, help=help_string)
    group.add_argument(*args, **kwargs)


def pprint_paths(specs: list["ResolvedSpec"]) -> None:
    unique_generators: dict[str, set[str]] = dict()
    for spec in specs:
        unique_generators.setdefault(str(spec.file_root), set()).add(str(spec.file_path))
    width = shutil.get_terminal_size().columns
    file = io.StringIO()
    console = rich.console.Console(file=file, width=width)
    for root, paths in unique_generators.items():
        console.print(Rule(title=f"[magenta]{root}[/magenta]"))
        columns = Columns(sorted(paths))
        console.print(columns)
    with console.pager():
        console.print(file.getvalue())


def pprint_files(specs: list["ResolvedSpec"]) -> None:
    console = rich.console.Console()
    columns = Columns(sorted(set([str(spec.file) for spec in specs])))
    with console.pager():
        console.print(columns)


def pprint_keywords(specs: list["ResolvedSpec"]) -> None:
    unique_kwds: dict[str, set[str]] = dict()
    for spec in specs:
        unique_kwds.setdefault(str(spec.file_root), set()).update(spec.keywords)
    width = shutil.get_terminal_size().columns
    file = io.StringIO()
    console = rich.console.Console(file=file, width=width)
    for root, kwds in unique_kwds.items():
        console.print(Rule(title=f"[magenta]{root}[/magenta]"))
        columns = Columns(sorted(kwds))
        console.print(columns)
    with console.pager():
        console.print(file.getvalue())


def pprint_graph(specs: list["ResolvedSpec"]) -> None:
    file = io.StringIO()
    graph.print(specs, file=file, style="rich")
    console = rich.console.Console()
    with console.pager():
        console.print(file.getvalue())


def pprint(specs: list["ResolvedSpec"]) -> None:
    tree: dict[str, list[str]] = {}
    for spec in specs:
        line = spec.display_name(style="rich", resolve=True)
        tree.setdefault(str(spec.file_root), []).append(line)
    width = shutil.get_terminal_size().columns
    file = io.StringIO()
    console = rich.console.Console(file=file, width=width)
    for root, lines in tree.items():
        console.print(Rule(f"[magenta]{root}[/magenta]"))
        columns = Columns(lines, expand=True)
        console.print(columns)
    with console.pager():
        console.print(file.getvalue())
