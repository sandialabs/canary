# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING

from ...util.editor import editor
from ...workspace import NotAWorkspaceError
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Edit())


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
    except Exception:  # nosec B110
        pass
    try:
        workspace = Workspace.load()
    except NotAWorkspaceError:
        return None
    case = workspace.find_testcase(testspec)
    return case.file
