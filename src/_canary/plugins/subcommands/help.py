import argparse
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Help()


class Help(CanarySubcommand):
    name = "help"
    description = "Get help on canary and its commands"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-a", "--all", action="store_true", help="list all available commands and options"
        )

    def execute(self, args: argparse.Namespace) -> int:
        from ... import config
        from ...config.argparsing import make_argument_parser

        parser = make_argument_parser()
        for command in config.plugin_manager.hook.canary_subcommand():
            parser.add_command(command, add_help_override=args.all)
        parser.print_help()
        return 0
