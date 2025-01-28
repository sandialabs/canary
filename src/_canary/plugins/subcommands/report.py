from argparse import Namespace

from ... import config
from ...config.argparsing import Parser
from ..hookspec import hookimpl
from ..types import CanarySubcommand


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return CanarySubcommand(
        name="report",
        description="Create and post test reports",
        setup_parser=setup_parser,
        execute=report,
        epilog=epilog,
    )


epilog = "Note: this command must be run from inside of a test session directory."


def setup_parser(parser: Parser) -> None:
    parent = parser.add_subparsers(dest="type", metavar="subcommands")
    for reporter in config.plugin_manager.hook.canary_reporter_subcommand():
        p = parent.add_parser(reporter.name, help=reporter.description)
        reporter.setup_parser(p)


def report(args: Namespace) -> int:
    for reporter in config.plugin_manager.hook.canary_reporter_subcommand():
        if reporter.name == args.type:
            reporter.execute(args)
            return 0
    else:
        raise ValueError(f"canary report: unknown subcommand {args.type!r}")
