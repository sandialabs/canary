# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING
from typing import Any

import yaml

from ...generator import AbstractTestGenerator
from ...third_party.color import colorize
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Describe())


class Describe(CanarySubcommand):
    name = "describe"
    description = "Print information about a test file, test case"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-o",
            dest="on_options",
            default=None,
            metavar="option",
            action="append",
            help="Turn option(s) on, such as '-o dbg' or '-o intel'",
        )
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        try:
            generator = AbstractTestGenerator.factory(args.testspec)
            describe_generator(generator, on_options=args.on_options)
            return 0
        except TypeError:
            pass

        # could be a test case in the test session?
        workspace = Workspace.load()
        case = workspace.locate(case=args.testspec)
        describe_testcase(case)
        return 0


def describe_generator(
    file: AbstractTestGenerator,
    on_options: list[str] | None = None,
) -> None:
    description = file.describe(on_options=on_options)
    print(colorize(description.rstrip()))


def dump(data: dict[str, Any]) -> str:
    return yaml.dump(data, default_flow_style=False)


def describe_testcase(case: "TestCase", indent: str = "") -> None:
    from pygments import highlight
    from pygments.formatters import (
        TerminalTrueColorFormatter as Formatter,  # ty: ignore[unresolved-import]
    )
    from pygments.lexers import get_lexer_by_name

    state = case.asdict()
    text = dump({"name": case.display_name(), **state})
    lexer = get_lexer_by_name("yaml")
    formatter = Formatter(bg="dark", style="monokai")
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)
