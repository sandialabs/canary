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
def canary_subcommand() -> CanarySubcommand:
    return Help()


class Help(CanarySubcommand):
    name = "help"
    description = "Get help on canary and its commands"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument("--all", action="store_true", help="list all commands and options")
        parser.add_argument("--pathspec", action="store_true", help="help on path spec syntax")

    def execute(self, args: argparse.Namespace) -> int:
        if args.pathspec:
            self.print_pathspec_help(args)
        else:
            self.print_command_help(args)
        return 0

    @staticmethod
    def print_command_help(args: argparse.Namespace) -> None:
        from ... import config
        from ...config.argparsing import make_argument_parser

        parser = make_argument_parser(all=args.all)
        parser.add_main_epilog(parser)
        for command in config.plugin_manager.hook.canary_subcommand():
            parser.add_command(command, add_help_override=args.all)
        parser.print_help()

    @staticmethod
    def print_pathspec_help(args: argparse.Namespace) -> None:
        from .common.pathspec import PathSpec

        print(PathSpec.description())
