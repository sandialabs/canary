# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import canary


@canary.hookimpl
def canary_subcommand() -> canary.CanarySubcommand:
    return MyCommand()


class MyCommand(canary.CanarySubcommand):
    name = "my-command"
    description = "My custom command"

    def setup_parser(self, parser: canary.Parser) -> None:
        parser.add_plugin_argument("--my-option")

    def my_command(self, args: argparse.Namespace) -> None:
        print(f"I am running my command with my-option={args.my_option}")
