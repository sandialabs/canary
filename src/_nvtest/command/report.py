from argparse import Namespace
from typing import Optional

from ..config.argparsing import Parser
from ..reporters import cli
from .command import Command


class Report(Command):
    @property
    def description(self) -> str:
        return "Generate test reports"

    @property
    def epilog(self) -> Optional[str]:
        return "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: Parser) -> None:
        cli.setup_parsers(parser)

    def execute(self, args: Namespace) -> int:
        return cli.main(args)
