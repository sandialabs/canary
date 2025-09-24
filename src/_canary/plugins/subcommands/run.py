# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import sys
from typing import TYPE_CHECKING

from ... import config
from ...util import graph
from ...util import logging
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
def canary_subcommand() -> CanarySubcommand:
    return Run()


class Run(CanarySubcommand):
    name = "run"
    description = "Find and run tests from a pathspec"
    epilog = "See canary help --pathspec for help on the path specification"

    def setup_parser(self, parser: "Parser") -> None:
        add_work_tree_arguments(parser)
        add_filter_arguments(parser)
        parser.add_argument("-u", "--until", choices=("discover", "lock"), help=argparse.SUPPRESS)
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
        from ...session import Session

        config.pluginmanager.hook.canary_runtests_startup(args=args)

        session: Session
        if args.mode == "w":
            path = args.work_tree or Session.default_worktree
            force = config.getoption("wipe") or False
            session = Session(path, mode=args.mode, force=force)
            if lockfile := getattr(args, "testcases_lock", None):
                session.load_from_lockfile(lockfile)
            else:
                session.add_search_paths(args.paths)
                parsing_policy = config.getoption("parsing_policy") or "pedantic"
                session.discover(pedantic=parsing_policy == "pedantic")
                if until := config.getoption("until"):
                    generators = session.generators
                    roots = set()
                    for generator in generators:
                        roots.add(generator.root)
                    n, N = len(generators), len(roots)
                    s, S = "" if n == 1 else "s", "" if N == 1 else "s"
                    logger.info("@*{Collected} %d file%s from %d root%s" % (n, s, N, S))
                    if until == "discover":
                        logger.info("Done with test discovery")
                        return 0
                env_mods = config.getoption("env_mods") or {}
                session.lock(
                    keyword_exprs=config.getoption("keyword_exprs"),
                    parameter_expr=config.getoption("parameter_expr"),
                    on_options=config.getoption("on_options"),
                    env_mods=env_mods.get("test") or {},
                    regex=config.getoption("regex_filter"),
                )

                if until := config.getoption("until"):
                    active_cases = session.get_ready()
                    n, N = len(active_cases), len({case.file for case in active_cases})
                    s, S = "" if n == 1 else "s", "" if N == 1 else "s"
                    logger.info("@*{Expanded} %d case%s from %d file%s" % (n, s, N, S))
                    graph.print(active_cases, file=sys.stdout)
                    if until == "lock":
                        logger.info("Done freezing test cases")
                        return 0
        elif args.mode == "a":
            case_specs = getattr(args, "case_specs", None)
            if case_specs and all([_.startswith("/") for _ in case_specs]):
                session = Session.casespecs_view(args.work_tree, case_specs)
            else:
                # use args here instead of config.getoption so that in-session runs can be filtered
                # with options not used during sesssion setup
                session = Session.filter_view(
                    args.work_tree,
                    start=args.start,
                    keyword_exprs=args.keyword_exprs,
                    parameter_expr=args.parameter_expr,
                    case_specs=case_specs,
                )
        else:
            raise ValueError(f"Unknown session mode {args.mode!r}")
        session.run()
        config.pluginmanager.hook.canary_runtests_summary(
            cases=session.active_cases(), include_pass=False, truncate=10
        )
        return session.exitstatus
