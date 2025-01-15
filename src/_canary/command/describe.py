import argparse
import os

import _canary.finder as finder
from _canary.config.argparsing import Parser
from _canary.generator import AbstractTestGenerator
from _canary.session import Session
from _canary.test.case import TestCase
from _canary.util import logging

from .base import Command
from .common import add_filter_arguments
from .common import add_resource_arguments


class Describe(Command):
    @property
    def description(self) -> str:
        return "Print information about a test file or test case"

    def setup_parser(self, parser: Parser):
        add_filter_arguments(parser)
        add_resource_arguments(parser)
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        if os.path.isdir(args.testspec):
            path = args.testspec
            return self.describe_folder(
                path,
                keyword_expr=args.keyword_expr,
                on_options=args.on_options,
                parameter_expr=args.parameter_expr,
            )
        if finder.is_test_file(args.testspec):
            file = finder.find(args.testspec)
            return self.describe_generator(file, on_options=args.on_options)
        # could be a test case in the test session?
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")
        for case in session.cases:
            if case.matches(args.testspec):
                self.describe_testcase(case)
                return 0
        print(f"{args.testspec}: could not find matching generator or test case")
        return 1

    @staticmethod
    def describe_folder(
        path: str,
        keyword_expr: str | None = None,
        on_options: list[str] | None = None,
        parameter_expr: str | None = None,
    ) -> int:
        f = finder.Finder()
        f.add(path)
        f.prepare()
        files = f.discover()
        for file in sorted(files, key=lambda f: f.file):
            Describe.describe_generator(file, on_options=on_options)
            print()
        return 0

    @staticmethod
    def describe_generator(
        file: AbstractTestGenerator,
        on_options: list[str] | None = None,
    ) -> int:
        description = file.describe(on_options=on_options)
        print(description.rstrip())
        return 0

    @staticmethod
    def describe_testcase(case: TestCase, indent: str = "") -> int:
        if case.work_tree is None:
            case.work_tree = "."
        d = dict(vars(case))
        d["status"] = (case.status.value, case.status.details)
        d["logfile"] = case.logfile()
        print(f"{indent}{case}")
        for key in sorted(d):
            if not key.startswith("_"):
                print(f"{indent}  {key}: {d[key]}")
        return 0
