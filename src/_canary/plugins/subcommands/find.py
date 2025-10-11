# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
from typing import TYPE_CHECKING

from ...error import StopExecution
from ...util import logging
from ...util.banner import banner
from ...util.filesystem import find_work_tree
from ...util.graph import static_order
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser

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
        add_group_argument(group, "graph", "Print DAG of test cases")
        add_group_argument(group, "lock", "Dump test cases to lock file")
        parser.add_argument(
            "--owner", dest="owners", action="append", help="Show tests owned by 'owner'"
        )
        add_filter_arguments(parser)
        add_resource_arguments(parser)
        PathSpec.setup_parser(parser)

    def execute(self, args: argparse.Namespace) -> int:
        from ... import config
        from ... import finder

        work_tree = find_work_tree(os.getcwd())
        if work_tree is not None:
            raise ValueError("find must be executed outside of a canary work tree")
        quiet = bool(args.print_files)
        if quiet:
            logging.set_level(logging.ERROR)
        else:
            logger.log(logging.EMIT, banner(), extra={"prefix": ""})
        f = finder.Finder()
        for root, paths in args.paths.items():
            f.add(root, *paths, tolerant=True)
        f.prepare()
        s = ", ".join(os.path.relpath(p, os.getcwd()) for p in f.roots)
        logger.info("@*{Searching} for tests in %s" % s)
        generators = f.discover()
        logger.debug(f"Discovered {len(generators)} test files")

        cases = finder.generate_test_cases(generators, on_options=args.on_options)

        config.pluginmanager.hook.canary_testsuite_mask(
            cases=cases,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            owners=None if not args.owners else set(args.owners),
            regex=args.regex_filter,
            case_specs=None,
            stage=None,
            start=None,
            ignore_dependencies=False,
        )
        for case in static_order(cases):
            config.pluginmanager.hook.canary_testcase_modify(case=case)
        cases_to_run = [case for case in cases if not case.wont_run()]
        if not cases_to_run:
            raise StopExecution("No tests to run", 7)
        if not quiet:
            config.pluginmanager.hook.canary_collectreport(cases=cases)
        cases_to_run.sort(key=lambda x: x.name)
        if args.print_paths:
            finder.pprint_paths(cases_to_run)
        elif args.print_files:
            finder.pprint_files(cases_to_run)
        elif args.print_graph:
            finder.pprint_graph(cases_to_run)
        elif args.print_lock:
            file = os.path.join(config.invocation_dir, "testcases.lock")
            states = [case.getstate() for case in cases_to_run]
            with open(file, "w") as fh:
                json.dump({"testcases": states}, fh, indent=2)
            logger.info("test cases written to testcase.lock")
        else:
            finder.pprint(cases_to_run)
        return 0


def add_group_argument(group, name, help_string, add_short_arg=True):
    args = [f"--{name}"]
    if add_short_arg:
        args.insert(0, f"-{name[0]}")
    kwargs = dict(dest=f"print_{name}", action="store_true", default=False, help=help_string)
    group.add_argument(*args, **kwargs)
