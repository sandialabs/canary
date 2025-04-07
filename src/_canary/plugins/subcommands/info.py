# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING
from typing import Any

import yaml

from ...test.case import TestCase
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Info()


class Info(CanarySubcommand):
    name = "info"
    description = "Print information about a test case"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        session = load_session()
        if args.testspec.startswith("^"):
            batch_id = args.testspec[1:]
            session.bfilter(batch_id=batch_id)
            cases = session.get_ready()
            describe_batch(batch_id, cases)
            return 0
        for case in session.cases:
            if case.matches(args.testspec):
                describe_testcase(case)
                return 0
        print(f"{args.testspec}: could not find matching generator or test case")
        return 1


def dump(data: dict[str, Any]) -> str:
    return yaml.dump(data, default_flow_style=False)


def describe_testcase(case: TestCase, indent: str = "") -> int:
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
    return 0


def describe_batch(batch_id: str, cases: list[TestCase]) -> int:
    from ... import config

    print(f"Batch {batch_id}")
    for case in cases:
        if case.work_tree is None:
            case.work_tree = config.session.work_tree
        print(f"{case.display_name}\n  {case.working_directory}")
    return 0
