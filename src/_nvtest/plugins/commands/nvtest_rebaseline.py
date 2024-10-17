import argparse
import os
from typing import Optional

from _nvtest.command import Command
from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging

from .common import filter_cases_by_path
from .common import filter_cases_by_status


class Rebaseline(Command):
    @property
    def description(self) -> str:
        return "Rebaseline tests"

    @property
    def epilog(self) -> Optional[str]:
        return "Note: this command must be run from inside of a test session directory."

    def setup_parser(self, parser: Parser):
        parser.add_argument("pathspec", nargs="?", help="Limit rebaselining to this path")

    def execute(self, args: argparse.Namespace) -> int:
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")
        cases: list[TestCase]
        if args.pathspec:
            cases = filter_cases_by_path(session.cases, args.pathspec)
        else:
            cases = filter_cases_by_status(session.cases, ("failed", "diffed"))
        for case in cases:
            case.do_baseline()
        return 0
