# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary report`` subcommand for generating reports in multiple formats."""

from argparse import Namespace
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..reporters.reporter import CanaryReporter
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Report())


class Report(CanarySubcommand):
    """Dispatch ``canary report <format>`` to the appropriate :class:`~.reporter.CanaryReporter` plugin."""

    name = "report"
    description = "Create reports from Canary results"

    def setup_parser(self, parser: "Parser") -> None:
        """Discover all reporter plugins and register each as a required subcommand."""
        reporters = self.collect_reporters()

        subparsers = parser.add_subparsers(dest="type", metavar="report-type", required=True)

        for reporter in reporters:
            p = subparsers.add_parser(reporter.type, help=reporter.description)
            reporter.setup_parser(p)
            p.set_defaults(_canary_reporter=reporter)

    def execute(self, args: Namespace) -> int:
        """Run the selected reporter plugin and return its exit code."""
        reporter = getattr(args, "_canary_reporter", None)
        if reporter is None:
            raise ValueError("canary report: missing report type")
        return reporter.run_from_args(args)

    @staticmethod
    def collect_reporters() -> list[CanaryReporter]:
        """Collect all registered :class:`~.reporter.CanaryReporter` instances, raising on duplicate types."""
        from .. import config

        reporters = list(config.pluginmanager.hook.canary_reporter())

        seen: set[str] = set()
        for reporter in reporters:
            if reporter.type in seen:
                raise ValueError(f"duplicate report type {reporter.type!r}")
            seen.add(reporter.type)

        return reporters
