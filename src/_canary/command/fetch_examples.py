import argparse
import importlib.resources as ir
import os

from _canary.config.argparsing import Parser
from _canary.util.filesystem import force_copy

from .base import Command


class Fetch(Command):
    @property
    def description(self) -> str:
        return "Fetch canary examples"

    @property
    def add_help(self) -> bool:
        return False

    def setup_parser(self, parser: Parser):
        parser.add_argument("what", choices=("examples", "canary.cmake"), type=str.lower)

    def execute(self, args: argparse.Namespace) -> int:
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
