# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING
from pathlib import Path

from ...hookspec import hookimpl
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


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
        parser.add_argument("testspec", help="Test name or test id")

    def execute(self, args: argparse.Namespace) -> int:
        from ...testcase import TestCase

        case: TestCase
        workspace = Workspace.load()
        case = workspace.find(case=args.testspec)
        f: Path | str
        if args.show_log:
            f = case.workspace.joinpath(case.stdout)
        elif args.show_input:
            f = case.file
        elif args.show_source_dir:
            f = case.file.parent
        elif args.show_working_directory:
            f = case.workspace.dir
        else:
            f = case.workspace.dir
        print(f)
        return 0
