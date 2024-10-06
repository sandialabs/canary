from argparse import Namespace
from typing import Optional

from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.reporter import Reporter


class Report(Command):
    @property
    def description(self) -> str:
        return "Create and post test reports"

    @property
    def epilog(self) -> Optional[str]:
        return "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: Parser) -> None:
        parent = parser.add_subparsers(dest="type", metavar="")
        for cls in Reporter.REGISTRY:
            p = parent.add_parser(cls.label().lower(), help=cls.description())
            cls.setup_parser(p)

    def execute(self, args: Namespace) -> int:
        for cls in Reporter.REGISTRY:
            if args.type == cls.label().lower():
                reporter = cls()
                reporter.execute(args)
                return 0
        else:
            raise ValueError(f"nvtest report: unknown subcommand {args.parent_command!r}")
