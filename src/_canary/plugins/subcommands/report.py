# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from argparse import Namespace
from typing import TYPE_CHECKING

from ...hookspec import hookimpl
from ..types import CanaryReporter
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Report())


class Report(CanarySubcommand):
    name = "report"
    description = "Create reports from Canary results"

    def setup_parser(self, parser: "Parser") -> None:
        reporters = self.collect_reporters()

        subparsers = parser.add_subparsers(dest="type", metavar="report-type", required=True)

        for reporter in reporters:
            p = subparsers.add_parser(reporter.type, help=reporter.description)
            reporter.setup_parser(p)
            p.set_defaults(_canary_reporter=reporter)

    def execute(self, args: Namespace) -> int:
        reporter = getattr(args, "_canary_reporter", None)
        if reporter is None:
            raise ValueError("canary report: missing report type")
        return reporter.run_from_args(args)

    @staticmethod
    def collect_reporters() -> list[CanaryReporter]:
        from ... import config

        reporters = list(config.pluginmanager.hook.canary_reporter())

        seen: set[str] = set()
        for reporter in reporters:
            if reporter.type in seen:
                raise ValueError(f"duplicate report type {reporter.type!r}")
            seen.add(reporter.type)

        return reporters
