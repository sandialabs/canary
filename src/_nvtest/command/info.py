import argparse
import os
from typing import Any

from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging

from .base import Command


class Info(Command):
    @property
    def description(self) -> str:
        return "Print information about a test case"

    def setup_parser(self, parser: Parser):
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")
        for case in session.cases:
            if case.matches(args.testspec):
                self.describe_testcase(case)
                return 0
        print(f"{args.testspec}: could not find matching generator or test case")
        return 1

    def dump(self, data: dict[str, Any]) -> str:
        try:
            import yaml

            return yaml.dump(data, default_flow_style=False)
        except ImportError:
            import json

            return json.dumps(data, indent=2)

    def describe_testcase(self, case: TestCase, indent: str = "") -> int:
        from pygments import highlight
        from pygments.formatters import TerminalTrueColorFormatter as Formatter
        from pygments.lexers import get_lexer_by_name

        if case.work_tree is None:
            case.work_tree = "."
        state = case.getstate()
        text = self.dump({"name": case.display_name, **state})
        lexer = get_lexer_by_name("yaml")
        formatter = Formatter(bg="dark", style="monokai")
        formatted_text = highlight(text.strip(), lexer, formatter)
        print(formatted_text)
        return 0
