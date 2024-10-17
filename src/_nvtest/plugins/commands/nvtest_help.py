import argparse

from _nvtest.abc import Command
from _nvtest.config.argparsing import Parser
from _nvtest.config.argparsing import make_argument_parser


class Help(Command):
    @property
    def description(self) -> str:
        return "Get help on nvtest and its commands"

    def setup_parser(self, parser: Parser):
        parser.add_argument(
            "-a", "--all", action="store_true", help="list all available commands and options"
        )

    def execute(self, args: argparse.Namespace) -> int:
        from _nvtest.plugin import add_all_commands

        parser = make_argument_parser()
        add_all_commands(parser, add_help_override=args.all)
        parser.print_help()
        return 0
