# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ... import config
from ... import when
from ...collect import Collector
from ...session import SessionResults
from ...util import logging
from ...workspace import NotAWorkspaceError
from ...workspace import SpecSelection
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Run())


class Run(CanarySubcommand):
    name = "run"
    description = "Find and run tests from a pathspec"
    epilog = "See canary help --pathspec for help on the path specification"

    def setup_parser(self, parser: "Parser") -> None:
        add_work_tree_arguments(parser)
        add_filter_arguments(parser)
        parser.add_argument(
            "--fail-fast",
            default=None,
            action="store_true",
            help="Stop after first failed test [default: %(default)s]",
        )
        parser.add_argument(
            "-P",
            "--parsing-policy",
            dest="parsing_policy",
            choices=("permissive", "pedantic"),
            help="If pedantic (default), stop if file parsing errors occur, else ignore parsing errors",
        )
        parser.add_argument(
            "--no-reset",
            "--dont-restage",
            dest="dont_restage",
            default=None,
            action="store_true",
            help="Do not return the test execution directory "
            "to its original stage before re-running a test",
        )
        parser.add_argument(
            "--copy-all-resources",
            default=None,
            action="store_true",
            help="Do not link resources to the test directory, only copy [default: %(default)s]",
        )
        parser.add_argument(
            "--dont-measure",
            default=None,
            action="store_true",
            help="Do not collect a test's process information [default: %(default)s]",
        )

        group = parser.add_argument_group("console reporting")
        group.add_argument(
            "--format",
            default="short",
            action="store",
            choices=["short", "long", "progress-bar"],
            help="Change the format of the test case's name as printed to the screen. "
            "Options are 'short' and 'long' [default: %(default)s]",
        )
        group.add_argument(
            "-e",
            choices=("separate", "merge"),
            default="separate",
            dest="testcase_output_strategy",
            help="Merge a testcase's stdout and stderr or log separately [default: %(default)s]",
        )
        group.add_argument(
            "--capture",
            choices=("log", "tee"),
            default="log",
            help="Log test output to a file only (log) or log and print output "
            "to the screen (tee).  Warning: this could result in a large amount of text printed "
            "to the screen [default: log]",
        )

        parser.add_argument("-r", help=argparse.SUPPRESS)
        add_resource_arguments(parser)
        Collector.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        config.pluginmanager.hook.canary_runtests_startup()

        workspace: Workspace
        selection: SpecSelection
        work_tree: str = args.work_tree or os.getcwd()
        if args.wipe:
            Workspace.remove(Path(work_tree))

        try:
            workspace = Workspace.load(Path(work_tree))
        except NotAWorkspaceError:
            workspace = Workspace.create(Path(work_tree))

        results: SessionResults | None = None
        if args.start:
            # Special case: re-run test cases from here down
            if args.parameter_expr:
                raise TypeError(f"{args.start}: parameter expression incompatible with start dir")
            if args.regex_filter:
                raise TypeError(f"{args.start}: regular expression incompatible with start dir")
            if args.tag:
                raise TypeError(f"{args.start}: tags incompatible with start dir")
            cases = workspace.select_from_path(path=Path(args.start))
            if args.keyword_exprs:
                cases = filter_cases_by_keyword(cases, args.keyword_exprs)
            with workspace.session(name=cases[0].workspace.session) as session:
                try:
                    results = session.run(ids=[case.id for case in cases])
                finally:
                    if results:
                        workspace.add_session_results(results)
        else:
            if args.runtag:
                selection = workspace.get_selection(args.runtag)
            elif args.specids:
                selection = workspace.select(ids=args.specids, tag=args.tag)
            elif args.scanpaths:
                parsing_policy = config.getoption("parsing_policy") or "pedantic"
                workspace.add(args.scanpaths, pedantic=parsing_policy == "pedantic")
                selection = workspace.select(
                    tag=args.tag,
                    keyword_exprs=args.keyword_exprs,
                    parameter_expr=args.parameter_expr,
                    on_options=args.on_options,
                    regex=args.regex_filter,
                )
            else:
                if any(
                    (args.keyword_exprs, args.parameter_expr, args.on_options, args.regex_filter)
                ):
                    selection = workspace.select(
                        tag=args.tag,
                        keyword_exprs=args.keyword_exprs,
                        parameter_expr=args.parameter_expr,
                        on_options=args.on_options,
                        regex=args.regex_filter,
                    )
                else:
                    # Get the default selection
                    selection = workspace.get_selection()

            with workspace.session(selection=selection) as session:
                try:
                    results = session.run()
                finally:
                    if results:
                        workspace.add_session_results(results)

        if not results:
            return 1
        config.pluginmanager.hook.canary_runtests_summary(
            cases=results.cases, include_pass=False, truncate=10
        )
        return results.returncode


def filter_cases_by_keyword(cases: list["TestCase"], keyword_exprs: list[str]) -> list["TestCase"]:
    masks: dict[str, bool] = {}
    for case in cases:
        kwds = set(case.spec.keywords)
        kwds.update(case.spec.implicit_keywords)  # ty: ignore[invalid-argument-type]
        kwd_all = (":all:" in keyword_exprs) or ("__all__" in keyword_exprs)
        if not kwd_all:
            for keyword_expr in keyword_exprs:
                match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                if not match:
                    masks[case.id] = True
                    break
    return [case for case in cases if not masks.get(case.id)]
