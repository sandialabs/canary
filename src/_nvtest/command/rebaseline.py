import argparse
import os

from _nvtest.config.argparsing import Parser
from _nvtest.session import Session
from _nvtest.test.case import TestCase
from _nvtest.util import logging

from .base import Command
from .common import filter_cases_by_path
from .common import filter_cases_by_status


class Rebaseline(Command):
    @property
    def description(self) -> str:
        return "Rebaseline tests"

    @property
    def epilog(self) -> str | None:
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
