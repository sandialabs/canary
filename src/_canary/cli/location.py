# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
from typing import TYPE_CHECKING

from ..app.paths import locate
from ..plugins.hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Location())


class Location(CanarySubcommand):
    name = "location"
    description = "Print locations of test files and directories"
    epilog = """\
If no options are give, -x is assumed."""

    def setup_parser(self, parser: "Parser") -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "-i",
            dest="show_input",
            action="store_true",
            default=False,
            help="Show the location of the test's input file",
        )
        group.add_argument(
            "-l",
            dest="show_log",
            action="store_true",
            default=False,
            help="Show the location of the test's log file",
        )
        group.add_argument(
            "-x",
            dest="show_working_directory",
            action="store_true",
            default=False,
            help="Show the location of the test's working directory",
        )
        group.add_argument(
            "-s",
            dest="show_source_dir",
            action="store_true",
            default=False,
            help="Show the location of the test's source directory",
        )
        parser.add_argument("--remap", default="auto", help="Path remapping mode")
        parser.add_argument("--json", action="store_true", default=False, help="Emit JSON output")
        parser.add_argument("testspec", nargs="+", help="Test name or test id")

    def execute(self, args: argparse.Namespace) -> int:
        testspecs = args.testspec if isinstance(args.testspec, list) else [args.testspec]
        items = locate(
            testspecs,
            show_input=args.show_input,
            show_source_dir=args.show_source_dir,
            show_log=args.show_log,
        )
        if getattr(args, "json", False):
            json.dump(items, fp=__import__("sys").stdout, indent=2)
            __import__("sys").stdout.write("\n")
            return 0
        for item in items:
            print(item["path"])
        return 0
