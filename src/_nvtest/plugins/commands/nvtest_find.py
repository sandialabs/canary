import argparse
import os

from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.finder import Finder
from _nvtest.session import Session
from _nvtest.util import logging
from _nvtest.util.banner import banner

from .common import PathSpec
from .common import add_mark_arguments
from .common import add_resource_arguments


class Find(Command):
    @property
    def description(self) -> str:
        return "Search paths for test files"

    def setup_parser(self, parser: Parser) -> None:
        group = parser.add_mutually_exclusive_group()
        self.add_group_argument(group, "paths", "Print file paths, grouped by root", False)
        self.add_group_argument(group, "files", "Print file paths")
        self.add_group_argument(group, "graph", "Print DAG of test cases")
        self.add_group_argument(group, "keywords", "Show available keywords", False)
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

    def execute(self, args: argparse.Namespace) -> int:
        logging.emit(banner() + "\n")
        search_paths = self.parse_search_paths(args)
        finder = Finder()
        for root, paths in search_paths.items():
            finder.add(root, *paths, tolerant=True)
        finder.prepare()
        generators = finder.discover()
        cases = Finder.lock(
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

    def add_group_argument(self, group, name, help_string, add_short_arg=True):
        args = [f"--{name}"]
        if add_short_arg:
            args.insert(0, f"-{name[0]}")
        kwargs = dict(dest=f"print_{name}", action="store_true", default=False, help=help_string)
        group.add_argument(*args, **kwargs)

    def parse_search_paths(self, args: argparse.Namespace) -> dict[str, list[str]]:
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
