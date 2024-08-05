import argparse

from ..config.argparsing import Parser
from ..config.argparsing import make_argument_parser

description = "Get help on nvtest and its commands"


def setup_parser(parser: Parser):
    parser.add_argument(
        "-a", "--all", action="store_true", help="list all available commands and options"
    )


def help(args: argparse.Namespace) -> int:
    from _nvtest.command import add_all_commands

    parser = make_argument_parser()
    add_all_commands(parser, add_help_override=args.all)
    parser.print_help()
    return 0
