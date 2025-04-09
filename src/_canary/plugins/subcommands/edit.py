# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING

from ...util.editor import editor
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Edit()


class Edit(CanarySubcommand):
    name = "edit"
    description = "open test files in $EDITOR"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        file = find_file(args.testspec)
        if file is None:
            print(f"{args.testspec}: no matching generator or test case found in {os.getcwd()}")
            return 1
        editor(file)
        return 0


def find_file(testspec: str) -> str | None:
    from ... import finder

    try:
        generator = finder.find(testspec)
        return generator.file
    except Exception:
        pass
    try:
        session = load_session()
    except Exception:
        return None
    for case in session.cases:
        if case.matches(testspec):
            return case.file
    return None
