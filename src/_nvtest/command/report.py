from argparse import Namespace

import _nvtest.reporter
from _nvtest.config.argparsing import Parser

from .base import Command


class Report(Command):
    @property
    def description(self) -> str:
        return "Create and post test reports"

    @property
    def epilog(self) -> str | None:
        return "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: Parser) -> None:
        parent = parser.add_subparsers(dest="type", metavar="")
        for reporter_t in _nvtest.reporter.reporters():
            p = parent.add_parser(reporter_t.label().lower(), help=reporter_t.description())
            reporter_t.setup_parser(p)

    def execute(self, args: Namespace) -> int:
        for reporter_t in _nvtest.reporter.reporters():
            if reporter_t.matches(args.type):
                reporter = reporter_t()
                reporter.execute(args)
                return 0
        else:
            raise ValueError(f"nvtest report: unknown subcommand {args.parent_command!r}")
