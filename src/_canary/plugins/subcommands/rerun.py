# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testspec import ResolvedSpec

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Rerun())


class Rerun(CanarySubcommand):
    name = "rerun"
    description = "rerun tests"

    def setup_parser(self, parser: "Parser") -> None:
        parser.set_defaults(banner=True)
        add_filter_arguments(parser)
        parser.add_argument(
            "--fail-fast",
            default=None,
            action="store_true",
            help="Stop after first failed test [default: %(default)s]",
        )
        parser.add_argument(
            "--copy-all-resources",
            default=None,
            action="store_true",
            help="Do not link resources to the test directory, only copy [default: %(default)s]",
        )
        parser.add_argument(
            "--only", default=None, choices=("failed", "all"), help="Only rerun these tests"
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
        parser.add_argument("paths", nargs=argparse.REMAINDER)

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        tag: str | None = None
        ids: list[str] = []
        if not args.paths:
            tag = "default"
        elif len(args.paths) == 1 and workspace.is_tag(args.paths[0]):
            tag = args.paths[0]
        else:
            found = workspace.find_specids(args.paths)
            for i, item in enumerate(found):
                if item is None:
                    raise ValueError(f"{args.paths[i]}: not a test spec ID")
                ids.append(item)

        specs: list["ResolvedSpec"]
        if tag:
            specs = workspace.get_selection(tag)
        else:
            specs = workspace.compute_rerun_list_for_specs(ids)
            if args.only is None:
                args.only = "include_all"
        only = args.only or "exclude_passed"

        # Convert to names used by selector
        if only == "all":
            only = "include_all"
        elif only == "ready":
            only = "only_ready"
        elif only == "failed":
            only = "only_failed"

        session = workspace.run(specs, only=only)
        return session.returncode
