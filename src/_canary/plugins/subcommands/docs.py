# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import webbrowser

from ...config.argparsing import Parser
from ...hookspec import hookimpl
from ..types import CanarySubcommand


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Docs())


class Docs(CanarySubcommand):
    name = "docs"
    description = "open canary documentation in a web browser"

    def execute(self, args: "argparse.Namespace") -> int:
        webbrowser.open("https://canary-wm.readthedocs.io/en/production/")
        return 0
