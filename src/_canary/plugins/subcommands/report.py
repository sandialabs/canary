# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from argparse import Namespace
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..types import CanaryReporter
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Report())


class Report(CanarySubcommand):
    name = "report"
    description = "Create and post test reports"

    def setup_parser(self, parser: "Parser") -> None:
        from ... import config

        subparsers = parser.add_subparsers(dest="type", metavar="subcommands")
        for reporter in config.pluginmanager.hook.canary_session_reporter():
            parent = subparsers.add_parser(reporter.type, help=reporter.description)
            reporter.setup_parser(parent)

    def execute(self, args: Namespace) -> int:
        from ... import config

        reporter: CanaryReporter
        for reporter in config.pluginmanager.hook.canary_session_reporter():
            if reporter.type == args.type:
                break
        else:
            raise ValueError(f"canary report: unknown report type {args.type!r}")

        kwargs = vars(args)
        action = getattr(reporter, args.action.replace("-", "_"), reporter.not_implemented)
        action(**kwargs)
