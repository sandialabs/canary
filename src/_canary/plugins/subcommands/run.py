# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ... import config
from ...collect import Collector
from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testspec import ResolvedSpec

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Run())


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
            "--copy-all-resources",
            default=None,
            action="store_true",
            help="Do not link resources to the test directory, only copy [default: %(default)s]",
        )

        group = parser.add_argument_group("console reporting")
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
        session = workspace.run(specs)
        return session.returncode

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
        specs = workspace.select_from_view(path=Path(start))
        filter_specs_by_keyword(specs, args)
        session = workspace.run(specs)
        return session.returncode

    def run_tag(self, path: Path, tag: str, args: "argparse.Namespace") -> int:
        workspace = Workspace.load(path)
        specs = workspace.get_selection(tag)
        session = workspace.run(specs)
        return session.returncode

    def run_specids(self, path: Path, specids: list[str], args: "argparse.Namespace") -> int:
        workspace = Workspace.load(path)
        specs = workspace.select(ids=specids, tag=args.tag)
        session = workspace.run(specs)
        return session.returncode

    def run_inplace(self, path: Path, args: "argparse.Namespace") -> int:
        # Load test cases, filter, and run
        workspace = Workspace.load(path)
        specs = workspace.select(
            tag=args.tag,
            keyword_exprs=args.keyword_exprs,
            parameter_expr=args.parameter_expr,
            on_options=args.on_options,
            regex=args.regex_filter,
        )
        session = workspace.run(specs)
        return session.returncode


def filter_specs_by_keyword(specs: list["ResolvedSpec"], args: "argparse.Namespace") -> None:
    from ... import rules
    from ...testspec import Mask

    if not args.keyword_exprs:
        return
    keyword_exprs = list(args.keyword_exprs)
    if (":all:" in keyword_exprs) or ("__all__" in keyword_exprs):
        return
    rule = rules.KeywordRule(keyword_exprs)
    for spec in specs:
        outcome = rule(spec)
        if not outcome:
            spec.mask = Mask.masked(outcome.reason or rule.default_reason)
    return
