import argparse

from ... import config
from ...config.argparsing import Parser
from ...config.argparsing import make_argument_parser
from ..hookspec import hookimpl
from ..types import CanarySubcommand


def setup_parser(parser: "Parser") -> None:
    parser.add_argument(
        "-a", "--all", action="store_true", help="list all available commands and options"
    )


def help(args: argparse.Namespace) -> int:
    parser = make_argument_parser()
    for command in config.plugin_manager.hook.canary_subcommand():
        parser.add_command(command, add_help_override=args.all)
    parser.print_help()
    return 0


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return CanarySubcommand(
        name="help",
        description="Get help on canary and its commands",
        setup_parser=setup_parser,
        execute=help,
    )
