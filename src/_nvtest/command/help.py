import argparse

from _nvtest.config.argparsing import Parser
from _nvtest.config.argparsing import make_argument_parser

from .base import Command


class Help(Command):
    @property
    def description(self) -> str:
        return "Get help on nvtest and its commands"

    def setup_parser(self, parser: Parser):
        parser.add_argument(
            "-a", "--all", action="store_true", help="list all available commands and options"
        )

    def execute(self, args: argparse.Namespace) -> int:
        parser = make_argument_parser()
        parser.add_all_commands(add_help_override=args.all)
        parser.print_help()
        return 0
