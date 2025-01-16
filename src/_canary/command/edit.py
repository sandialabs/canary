import argparse
import os

import _canary.finder as finder
from _canary.config.argparsing import Parser
from _canary.session import Session
from _canary.util import logging
from _canary.util.editor import editor

from .base import Command


class Edit(Command):
    @property
    def description(self) -> str:
        return "open test files in $EDITOR"

    def setup_parser(self, parser: Parser):
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        file = find_file(args.testspec)
        if file is None:
            print(f"{args.testspec}: no matching generator or test case found in {os.getcwd()}")
            return 1
        editor(file)
        return 0


def find_file(testspec: str) -> str | None:
    try:
        generator = finder.find(testspec)
        return generator.file
    except Exception:
        pass
    try:
        with logging.level(logging.WARNING):
            session = Session(os.getcwd(), mode="r")
    except Exception:
        return None
    for case in session.cases:
        if case.matches(testspec):
            return case.file
    return None
