# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING
from typing import Any

import yaml

from ...generator import AbstractTestGenerator
from ...test.case import TestCase
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Describe()


class Describe(CanarySubcommand):
    name = "describe"
    description = "Print information about a test file, test case, or test batch"

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
        import _canary.finder as finder

        if args.testspec.startswith("^"):
            session = load_session()
            batch_id = args.testspec[1:]
            session.bfilter(batch_id=batch_id)
            cases = session.get_ready()
            describe_batch(batch_id, cases)
            return 0

        if finder.is_test_file(args.testspec):
            file = finder.find(args.testspec)
            describe_generator(file, on_options=args.on_options)
            return 0

        # could be a test case in the test session?
        session = load_session()
        for case in session.cases:
            if case.matches(args.testspec):
                describe_testcase(case)
                return 0

        print(f"{args.testspec}: could not find matching generator or test case")
        return 1


def describe_generator(
    file: AbstractTestGenerator,
    on_options: list[str] | None = None,
) -> None:
    description = file.describe(on_options=on_options)
    print(description.rstrip())


def dump(data: dict[str, Any]) -> str:
    return yaml.dump(data, default_flow_style=False)


def describe_testcase(case: TestCase, indent: str = "") -> None:
    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter as Formatter
    from pygments.lexers import get_lexer_by_name

    if case.work_tree is None:
        case.work_tree = "."
    state = case.getstate()
    text = dump({"name": case.display_name, **state})
    lexer = get_lexer_by_name("yaml")
    formatter = Formatter(bg="dark", style="monokai")
    formatted_text = highlight(text.strip(), lexer, formatter)
    print(formatted_text)


def describe_batch(batch_id: str, cases: list[TestCase]) -> None:
    from ... import config

    print(f"Batch {batch_id}")
    for case in cases:
        if case.work_tree is None:
            case.work_tree = config.session.work_tree
        print(f"{case.display_name}\n  {case.working_directory}")
