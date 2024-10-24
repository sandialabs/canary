import argparse
import os
from typing import Optional

from _nvtest.config.argparsing import Parser
from _nvtest.resource import ResourceHandler
from _nvtest.runners import TestCaseRunner
from _nvtest.session import Session
from _nvtest.test.case import TestCase

from .base import Command
from .common import filter_cases_by_path
from .common import filter_cases_by_status


class Analyze(Command):
    @property
    def description(self) -> str:
        return "Run the analysis section of tests by passing \
    ``--execute-analysis-sections`` to their command line"

    @property
    def epilog(self) -> Optional[str]:
        return """\
An "analyze" run only makes sense in the following conditions:

1. The test has already been run; and
2. The test has logic for handling ``--execute-analysis-sections`` on the command line.

No attempt is made to determine whether the second condition is met.

Note: this command must be run in a test session directory.
"""

    def setup_parser(self, parser: Parser):
        parser.add_argument("pathspec", nargs="?", help="Limit analyis to tests in this path")

    def execute(self, args: argparse.Namespace) -> int:
        session = Session(os.getcwd(), mode="r")
        cases: list[TestCase]
        if args.pathspec:
            cases = filter_cases_by_path(session.cases, args.pathspec)
        else:
            cases = filter_cases_by_status(session.cases, ("failed", "diffed", "success"))
        rh = ResourceHandler()
        runner = TestCaseRunner(rh)
        for case in cases:
            runner.analyze(case)
        return 0
