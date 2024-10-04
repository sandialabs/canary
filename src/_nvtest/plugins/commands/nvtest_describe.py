import argparse
import os

import _nvtest.finder as finder
from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.util import logging
from _nvtest.command import Command
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
        try:
            return self.describe_generator(args)
        except Exception:
            try:
                return self.describe_testcase(args)
            except Exception:
                pass
        print(f"{args.testspec}: could not find matching generator or test case")
        return 1

    def describe_generator(self, args: argparse.Namespace) -> int:
        file = finder.find(args.testspec)
        description = file.describe(
            keyword_expr=args.keyword_expr, on_options=args.on_options, rh=args.rh
        )
        print(description.rstrip())
        return 0

    def describe_testcase(self, args: argparse.Namespace) -> int:
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")
        for case in session.cases:
            if case.matches(args.testspec):
                d = dict(vars(case))
                d["status"] = (case.status.value, case.status.details)
                d["logfile"] = case.logfile()
                print(case)
                for key in sorted(d):
                    if not key.startswith("_"):
                        print(f"  {key}: {d[key]}")
                return 0
        return -1
