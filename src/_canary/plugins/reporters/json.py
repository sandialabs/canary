import argparse
import json
import os

from ...config.argparsing import Parser
from ..hookspec import hookimpl
from ..types import CanaryReporterSubcommand
from .common import load_session


@hookimpl
def canary_reporter_subcommand() -> CanaryReporterSubcommand:
    return CanaryReporterSubcommand(
        name="json",
        description="JSON reporter",
        setup_parser=setup_parser,
        execute=create_json_report,
    )


def setup_parser(parser: Parser) -> None:
    sp = parser.add_subparsers(dest="subcommand", metavar="subcommands")
    p = sp.add_parser("create", help="Create JSON report")
    p.add_argument("-o", dest="output", help="Output file name", default="Results.json")


def create_json_report(args: argparse.Namespace) -> None:
    if args.subcommand == "create":
        file = os.path.abspath(args.output)
        data: dict = {}
        session = load_session()
        for case in session.cases:
            data[case.id] = case.getstate()
        with open(file, "w") as fh:
            json.dump(data, fh, indent=2)
    else:
        raise ValueError(f"{args.subcommand}: unknown JSON report subcommand")
