import json
import os
from typing import Optional

from _nvtest.session import Session
from _nvtest.test.case import getstate as get_testcase_state
from _nvtest.util import logging

from .base import Reporter


def setup_parser(parser):
    sp = parser.add_subparsers(dest="child_command", metavar="")
    sp.add_parser("create", help="Create json report")


def create_report(args):
    with logging.level(logging.WARNING):
        session = Session(os.getcwd(), mode="r")
    reporter = JsonReporter(session)
    if args.child_command == "create":
        reporter.create()
    else:
        raise ValueError(f"{args.child_command}: unknown `nvtest report json` subcommand")


class JsonReporter(Reporter):
    def __init__(self, session: Session, dest: Optional[str] = None) -> None:
        super().__init__(session)
        self.file = os.path.join(session.root, "Results.json")

    def create(self) -> None:
        """Collect information and create reports"""
        data: dict = {}
        for case in self.data.cases:
            data[case.id] = get_testcase_state(case)
        with open(self.file, "w") as fh:
            json.dump(data, fh, indent=2)
