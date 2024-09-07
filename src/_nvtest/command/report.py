from argparse import Namespace

from ..config.argparsing import Parser
from ..reporters import cli

description = "Generate test reports"
epilog = "Note: this command must be run from inside of a test session directory."


def setup_parser(parser: Parser) -> None:
    cli.setup_parsers(parser)


def report(args: Namespace) -> int:
    return cli.main(args)
