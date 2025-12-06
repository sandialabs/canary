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
from ...hookspec import hookimpl
from ...session import SessionResults
from ...util import logging
from ...workspace import Workspace
from ...util.graph import reachable_nodes
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

ok_status = ("SKIPPED", "SUCCESS", "XDIFF", "XFAIL", "TIMEOUT")


class Run(CanarySubcommand):
    name = "run"
    description = "Find and run tests from a pathspec"
    epilog = "See canary help --pathspec for help on the path specification"

    def setup_parser(self, parser: "Parser") -> None:
        parser.set_defaults(banner=True)
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
        parser.add_argument(
            "--rerun-failed",
            action="store_true",
            help="Rerun failed tests [default: False]",
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
        work_tree = args.work_tree or os.getcwd()
        if args.wipe:
            Workspace.remove(work_tree)
        if path := Workspace.find_workspace(work_tree):
            return self.run_inworkspace(path, args)
        else:
            return self.create_workspace_and_run(args)

    def create_workspace_and_run(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.create(args.work_tree or os.getcwd())
        if args.start:
            raise ValueError("Illegal option in new workspace: 'start'")
        if args.runtag:
            raise ValueError("Illegal option in new workspace: 'runtag'")
        if args.specids:
            raise ValueError("Illegal option in new workspace: 'specids'")
        scanpaths = args.scanpaths or {os.getcwd(): []}
        parsing_policy = config.getoption("parsing_policy") or "pedantic"
        workspace.add(scanpaths, pedantic=parsing_policy == "pedantic")
        specs = workspace.select(
            tag=args.tag,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
        )
        results: SessionResults = workspace.run(specs)
        return results.returncode

    def run_inworkspace(self, path: Path, args: "argparse.Namespace") -> int:
        """The workspace already exists, now let's run some test cases within it"""
        if args.scanpaths:
            raise ValueError("Add new scanpaths to workspace with 'canary add ...'")
        opts = ("start", "runtag", "specids")
        defined = [o for o in opts if getattr(args, o, None) is not None]
        if len(defined) > 1:
            raise ValueError(f"only one of {', '.join(defined)} may be provided")
        if args.start:
            return self.run_inview(path, args.start, args)
        elif args.runtag:
            return self.run_tag(path, args.runtag, args)
        elif args.specids:
            return self.run_specids(path, args.specids, args)
        else:
            return self.run_inplace(path, args)

    def run_inview(self, path: Path, start: str, args: "argparse.Namespace") -> int:
        workspace = Workspace.load(path)
        if args.parameter_expr:
            raise TypeError(f"{start}: parameter expression incompatible with start dir")
        if args.regex_filter:
            raise TypeError(f"{start}: regular expression incompatible with start dir")
        if args.tag:
            raise TypeError(f"{start}: tags incompatible with start dir")
        cases = workspace.select_from_view(path=Path(start))
        cases = filter_cases(cases, args)
        if len({case.workspace.session for case in cases}) > 1:
            raise ValueError("All cases must come from the same session")
        results: SessionResults | None = None
        with workspace.session(name=cases[0].workspace.session) as session:
            try:
                results = session.run(ids=[case.id for case in cases])
            finally:
                if results:
                    workspace.add_session_results(results)
        if not results:
            return 1
        return results.returncode

    def run_tag(self, path: Path, tag: str, args: "argparse.Namespace") -> int:
        workspace = Workspace.load(path)
        specs = workspace.get_selection(tag)
        results: SessionResults | None = None
        with workspace.session(specs=specs) as session:
            try:
                results = session.run()
            finally:
                if results:
                    workspace.add_session_results(results)
        if not results:
            return 1
        return results.returncode

    def run_specids(self, path: Path, specids: list[str], args: "argparse.Namespace") -> int:
        workspace = Workspace.load(path)
        specs = workspace.select(ids=specids, tag=args.tag)
        results: SessionResults | None = None
        with workspace.session(specs=specs) as session:
            try:
                results = session.run()
            finally:
                if results:
                    workspace.add_session_results(results)
        if not results:
            return 1
        return results.returncode


    def run_inplace(self, path: Path, args: "argparse.Namespace") -> int:
        # Load test cases, filter, and run
        workspace = Workspace.load(path)
        results: SessionResults | None = None
        specs = workspace.select(
            tag=args.tag,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
        )
        if args.rerun_failed:
            ids = workspace.find_failed()
        with workspace.session(specs=specs) as session:
            try:
                results = session.run()
            finally:
                if results:
                    workspace.add_session_results(results)
        if not results:
            return 1
        return results.returncode


def filter_failed_cases(workspace: Workspace, cases: list["TestCase"]) -> list["TestCase"]:
    graph = {spec.id: [dep.id for dep in spec.dependencies] for spec in specs}
    failed: set[str] = set()
    cases = workspace.load_testcases(ids=[spec.id for spec in specs])
    map: dict[str, "TestCase"] = {case.id: case for case in cases}
    for case in cases:
        if case.status.category not in ok_status:
            failed.add(case.id)
    reachable = reachable_nodes(graph, failed)
    #specs = [spec for spec in specs if spec.id in reachable and ]


def filter_cases(cases: list["TestCase"], args: "argparse.Namespace") -> list["TestCase"]:
    keyword_exprs = args.keyword_exprs or []
    if (":all:" in keyword_exprs) or ("__all__" in keyword_exprs):
        return cases
    masks: dict[str, bool] = {}
    for case in cases:
        kwds = set(case.spec.keywords)
        kwds.update(case.spec.implicit_keywords)  # ty: ignore[invalid-argument-type]
        if args.rerun_failed and case.status.category in ok_status:
            # skip passing tests
            masks[case.id] = True
            continue
        for keyword_expr in keyword_exprs:
            match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
            if not match:
                masks[case.id] = True
                break
    return [case for case in cases if not masks.get(case.id)]
