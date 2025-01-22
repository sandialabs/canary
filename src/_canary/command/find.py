import argparse
import os
import time

from .. import finder
from .. import plugin
from ..config.argparsing import Parser
from ..error import StopExecution
from ..session import ExitCode
from ..session import Session
from ..third_party.color import colorize
from ..util import logging
from ..util.banner import banner
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
        else:
            logging.emit(banner() + "\n")
        self.parse_search_paths(args)
        f = finder.Finder()
        for root, paths in args.paths.items():
            f.add(root, *paths, tolerant=True)
        f.prepare()
        s = ", ".join(os.path.relpath(p, os.getcwd()) for p in f.roots)
        logging.info(colorize("@*{Searching} for tests in %s" % s))
        generators = f.discover()
        logging.debug(f"Discovered {len(generators)} test files")

        cases = finder.generate_test_cases(generators, on_options=args.on_options)

        logging.info(colorize("@*{Masking} test cases based on filtering criteria..."), end="")
        start = time.monotonic()
        finder.mask(
            cases,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            owners=None if not args.owners else set(args.owners),
            regex=args.regex_filter,
        )
        for p in plugin.hooks():
            for case in cases:
                p.test_discovery(case)
        dt = time.monotonic() - start
        logging.info(
            colorize("@*{Masking} test cases based on filtering criteria... done (%.2fs.)" % dt),
            rewind=True,
        )
        finder.check_for_skipped_dependencies(cases)
        cases_to_run = [case for case in cases if not case.masked()]
        masked = [case for case in cases if case.masked()]
        logging.info(colorize("@*{Selected} %d test cases" % (len(cases) - len(masked))))
        if masked and not args.print_files:
            Session.report_excluded(masked)
        if not cases_to_run:
            raise StopExecution("No tests to run", ExitCode.NO_TESTS_COLLECTED)
        cases_to_run.sort(key=lambda x: x.name)
        if args.print_keywords:
            finder.pprint_keywords(cases_to_run)
        elif args.print_paths:
            finder.pprint_paths(cases_to_run)
        elif args.print_files:
            finder.pprint_files(cases_to_run)
        elif args.print_graph:
            finder.pprint_graph(cases_to_run)
        else:
            finder.pprint(cases_to_run)
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
