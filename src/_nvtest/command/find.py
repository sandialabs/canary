import argparse

from _nvtest.config.argparsing import Parser
from _nvtest.finder import Finder
from _nvtest.util import logging
from _nvtest.util.banner import banner

from .base import Command
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments


class Find(Command):
    @property
    def description(self) -> str:
        return "Search paths for test files"

    def setup_parser(self, parser: Parser) -> None:
        group = parser.add_mutually_exclusive_group()
        self.add_group_argument(group, "paths", "Print file paths, grouped by root", False)
        self.add_group_argument(group, "files", "Print file paths", False)
        self.add_group_argument(group, "graph", "Print DAG of test cases")
        self.add_group_argument(group, "keywords", "Show available keywords", False)
        parser.add_argument(
            "--owner", dest="owners", action="append", help="Show tests owned by 'owner'"
        )
        add_filter_arguments(parser)
        add_resource_arguments(parser)
        PathSpec.setup_parser(parser)

    def execute(self, args: argparse.Namespace) -> int:
        if args.print_files:
            logging.set_level(logging.ERROR)
        logging.emit(banner() + "\n")
        self.parse_search_paths(args)
        finder = Finder()
        for root, paths in args.paths.items():
            finder.add(root, *paths, tolerant=True)
        finder.prepare()
        generators = finder.discover()
        cases = finder.lock_and_filter(
            generators,
            keyword_expr=args.keyword_expr,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            owners=None if not args.owners else set(args.owners),
            env_mods=args.env_mods.get("test") or {},
            regex=args.regex_filter,
        )
        cases_to_run = [case for case in cases if not case.mask]
        cases_to_run.sort(key=lambda x: x.name)
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

    def add_group_argument(self, group, name, help_string, add_short_arg=True):
        args = [f"--{name}"]
        if add_short_arg:
            args.insert(0, f"-{name[0]}")
        kwargs = dict(dest=f"print_{name}", action="store_true", default=False, help=help_string)
        group.add_argument(*args, **kwargs)

    def parse_search_paths(self, args: argparse.Namespace) -> None:
        on_options: list[str] = []
        pathspec: list[str] = []
        for item in args.pathspec:
            if item.startswith("+"):
                on_options.append(item[1:])
            else:
                pathspec.append(item)
        args.pathspec = pathspec
        args.on_options.extend(on_options)
        PathSpec.parse_new_session(args)
