import argparse
import os
from typing import Optional

import _nvtest.finder as finder
from _nvtest.abc import AbstractTestGenerator
from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.resource import ResourceHandler
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging

from .common import add_mark_arguments
from .common import add_resource_arguments


class Describe(Command):
    @property
    def description(self) -> str:
        return "Print information about a test file or test case"

    def setup_parser(self, parser: Parser):
        add_mark_arguments(parser)
        add_resource_arguments(parser)
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        if os.path.isdir(args.testspec):
            path = args.testspec
            return self.describe_folder(
                path,
                keyword_expr=args.keyword_expr,
                on_options=args.on_options,
                rh=args.rh,
                parameter_expr=args.parameter_expr,
            )
        if finder.is_test_file(args.testspec):
            file = finder.find(args.testspec)
            return self.describe_generator(
                file,
                keyword_expr=args.keyword_expr,
                on_options=args.on_options,
                rh=args.rh,
                parameter_expr=args.parameter_expr,
            )
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
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> int:
        f = finder.Finder()
        f.add(path)
        f.prepare()
        files = f.discover()
        for file in sorted(files, key=lambda f: f.file):
            Describe.describe_generator(
                file,
                keyword_expr=keyword_expr,
                parameter_expr=parameter_expr,
                on_options=on_options,
                rh=rh,
            )
            print()
        return 0

    @staticmethod
    def describe_generator(
        file: AbstractTestGenerator,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> int:
        description = file.describe(
            keyword_expr=keyword_expr, on_options=on_options, rh=rh, parameter_expr=parameter_expr
        )
        print(description.rstrip())
        return 0

    @staticmethod
    def describe_testcase(case: TestCase, indent: str = "") -> int:
        if case.exec_root is None:
            case.exec_root = "."
        d = dict(vars(case))
        d["status"] = (case.status.value, case.status.details)
        d["logfile"] = case.logfile()
        print(f"{indent}{case}")
        for key in sorted(d):
            if not key.startswith("_"):
                print(f"{indent}  {key}: {d[key]}")
        return 0
