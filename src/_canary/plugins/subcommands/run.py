# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ... import config
from ...util import logging
from ...workspace import CaseSelection
from ...workspace import NotAWorkspaceError
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import PathSpec
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import add_work_tree_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser

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
        PathSpec.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        config.pluginmanager.hook.canary_runtests_startup()

        workspace: Workspace
        selection: CaseSelection
        work_tree: str = args.work_tree or os.getcwd()
        if args.wipe:
            Workspace.remove(Path(work_tree))
        try:
            workspace = Workspace.load()
        except NotAWorkspaceError:
            workspace = Workspace.create(Path(work_tree))

        if args.runtag:
            selection = workspace.get_selection(args.runtag)
        elif args.casespecs:
            selection = workspace.select_testcases(args.casespecs, tag=args.tag)
        elif args.paths:
            parsing_policy = config.getoption("parsing_policy") or "pedantic"
            workspace.add(args.paths, pedantic=parsing_policy == "pedantic")
            tag = workspace.tag(
                args.tag,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                on_options=args.on_options,
                regex=args.regex_filter,
            )
            selection = workspace.get_selection(tag)
        else:
            if any((args.keyword_exprs, args.parameter_expr, args.on_options, args.regex_filter)):
                tag = workspace.tag(
                    args.tag,
                    keyword_exprs=args.keyword_exprs,
                    parameter_expr=args.parameter_expr,
                    on_options=args.on_options,
                    regex=args.regex_filter,
                )
                selection = workspace.get_selection(tag)
            else:
                selection = workspace.get_selection()

        # FIXME: env_mods = config.getoption("env_mods") or {}
        with workspace.session(selection=selection) as session:
            disp = session.run()

        config.pluginmanager.hook.canary_runtests_summary(
            cases=disp["cases"], include_pass=False, truncate=10
        )
        return disp["returncode"]
