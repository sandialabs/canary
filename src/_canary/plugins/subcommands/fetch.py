import argparse
import importlib.resources as ir
import os

from ...config.argparsing import Parser
from ...util.filesystem import force_copy
from ..hookspec import hookimpl
from ..types import CanarySubcommand


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return CanarySubcommand(
        name="fetch",
        description="Fetch canary assets",
        setup_parser=setup_parser,
        execute=fetch,
    )


def setup_parser(parser: "Parser") -> None:
    parser.add_argument("what", choices=("examples", "canary.cmake"), type=str.lower)


def fetch(args: argparse.Namespace) -> int:
    if args.what == "examples":
        path = str(ir.files("canary").joinpath("examples"))
        if os.path.exists("examples"):
            raise ValueError(f"A folder named 'examples' already exists at {os.getcwd()}")
        force_copy(path, os.path.basename(path))
    elif args.what.lower() == "canary.cmake":
        path = str(ir.files("canary").joinpath("tools/Canary.cmake"))
        with open(os.path.basename(path), "w") as fh:
            fh.write(open(path).read())
    else:
        raise ValueError(f"Unknown option to fetch {args.what!r}")
    return 0
