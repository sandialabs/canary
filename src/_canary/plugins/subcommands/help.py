# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Help())


class Help(CanarySubcommand):
    name = "help"
    description = "Get help on canary and its commands"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument("--all", action="store_true", help="list all commands and options")
        parser.add_argument("--pathspec", action="store_true", help="help on path spec syntax")
        parser.add_argument("--pathfile", action="store_true", help="help on path file syntax")

    def execute(self, args: argparse.Namespace) -> int:
        if args.pathspec:
            self.print_pathspec_help(args)
        elif args.pathfile:
            self.print_pathfile_help(args)
        else:
            self.print_command_help(args)
        return 0

    @staticmethod
    def print_command_help(args: argparse.Namespace) -> None:
        from ... import config
        from ...config.argparsing import make_argument_parser

        parser = make_argument_parser(all=args.all)
        parser.add_main_epilog(parser)
        config.pluginmanager.hook.canary_addcommand(parser=parser)
        parser.print_help()

    @staticmethod
    def print_pathspec_help(args: argparse.Namespace) -> None:
        from ...collect import PathSpec

        print(PathSpec.pathspec_help())

    @staticmethod
    def print_pathfile_help(args: argparse.Namespace) -> None:
        from ...collect import PathSpec

        print(PathSpec.pathfile_help())
