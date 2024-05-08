import json
import os
from typing import Optional

import nvtest
from _nvtest.session import Session
from _nvtest.util import logging

from .reporter import Reporter


@nvtest.plugin.register(scope="report", stage="setup", type="json")
def setup_parser(parser):
    sp = parser.add_subparsers(dest="child_command", metavar="")
    sp.add_parser("create", help="Create CDash XML files")


@nvtest.plugin.register(scope="report", stage="create", type="json")
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
        data = {}
        for case in self.data.cases:
            d = data.setdefault(case.id, {})
            for var, val in vars(case).items():
                if var.startswith("_"):
                    continue
                d[var] = val
            d["keywords"] = case.keywords()
            d["status"] = {"value": case.status.value, "details": case.status.details}
            d["dependencies"] = [dep.id for dep in case.dependencies]
        with open(self.file, "w") as fh:
            json.dump(data, fh, indent=2)
