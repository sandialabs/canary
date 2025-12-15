# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ... import config
from ...collect import Collector
from ...generate import Generator
from ...hookspec import hookimpl
from ...select import Selector
from ...util import logging
from ...workspace import NotAWorkspaceError
from ...workspace import Workspace
from ..types import CanarySubcommand
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
        Collector.setup_parser(parser)
        Generator.setup_parser(parser)
        Selector.setup_parser(parser)
        parser.add_argument(
            "--only",
            choices=("not_done", "failed", "all"),
            default="not_done",
            help="Which tests to run after selection\n\n"
            "  all      - run all selected tests, even if already passing\n\n"
            "  failed   - run only previously failing tests\n\n"
            "  new      - run tests that have never been executed\n\n"
            "  not_done - run tests that are incomplete, boken, or never run (default)",
        )
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
        group.add_argument(
            "--format",
            dest="live_name_fmt",
            choices=("long", "short"),
            default="short",
            help="Print test case fullname (long) in live status bar [default: short]",
        )
        add_resource_arguments(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        work_tree = args.work_tree or os.getcwd()
        if args.wipe:
            Workspace.remove(work_tree)
        workspace: Workspace
        reuse: bool = False
        try:
            workspace = Workspace.load(start=work_tree)
        except NotAWorkspaceError:
            workspace = Workspace.create(path=work_tree)
        # start, specids, runtag, and scanpaths are mutually exclusive
        specs: list["ResolvedSpec"]
        if args.scanpaths is not None:
            parsing_policy = config.getoption("parsing_policy") or "pedantic"
            workspace.find_and_add_generators(args.scanpaths, pedantic=parsing_policy == "pedantic")
            workspace.generate_testspecs(on_options=args.on_options)
            specs = workspace.make_selection(
                tag=args.tag,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
            )
        else:
            if args.start:
                logger.info(f"[bold]Running[/] tests from {args.start}")
                specs = workspace.select_from_view(path=Path(args.start))
                reuse = True
            elif args.specids:
                specs_to_run = [id[:7] for id in args.specids]
                if len(specs_to_run) > 3:
                    specs_to_run = [*specs_to_run[:2], "...", specs_to_run[-1]]
                logger.info(f"[bold]Running[/] specs {', '.join(specs_to_run)}")
                specs = workspace.make_selection(ids=args.specids, tag=args.tag)
            elif args.runtag:
                logger.info(f"[bold]Running[/] tests in tag {args.runtag}")
                specs = workspace.get_selection(args.runtag)
            else:
                # scanpaths must be explicit
                args.runtag = "default"
                logger.info(f"[bold]Running[/] tests in tag {args.runtag}")
                specs = workspace.get_selection(args.runtag)
            # Apply additional filters, if any
            workspace.apply_selection_rules(
                specs,
                keyword_exprs=args.keyword_exprs,
                parameter_expr=args.parameter_expr,
                owners=args.owners,
                regex=args.regex_filter,
                tag=args.tag,
            )
        session = workspace.run(specs, reuse_session=reuse, only=args.only)
        return session.returncode


class StatusFormatAction(argparse.Action):
    _choices: list[str] = [
        "ID",
        "FullName",
        "Name",
        "Duration",
        "Status",
        "Details",
        "Rank",
    ]

    def __call__(self, parser, namespace, value, option_string=None):
        items = value.split(",")
        for i, item in enumerate(items):
            if choice := match_case_insensitive(item, self._choices):
                items[i] = choice
            else:
                choices = ",".join(self._choices)
                parser.error(f"Invalid status format {item!r}, choose from {choices}")
        value = ",".join(items)
        setattr(namespace, self.dest, value)


def match_case_insensitive(s: str, choices: list[str]) -> str | None:
    for choice in choices:
        if s.lower() == choice.lower():
            return choice
    return None
