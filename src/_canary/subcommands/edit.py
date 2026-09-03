# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary edit`` subcommand for opening a test file in ``$EDITOR``."""

import argparse
import os
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..util.editor import editor
from ..workspace import NotAWorkspaceError
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Edit())


class Edit(CanarySubcommand):
    """Look up the source file for a test spec and open it in the user's ``$EDITOR``."""

    name = "edit"
    description = "open test files in $EDITOR"

    def setup_parser(self, parser: "Parser") -> None:
        """Register the ``testspec`` positional argument."""
        parser.add_argument("testspec", help="Job file or job spec")

    def execute(self, args: argparse.Namespace) -> int:
        """Resolve the test spec to a file and open it in ``$EDITOR``, returning 1 if not found."""
        file = find_file(args.testspec)
        if file is None:
            print(f"{args.testspec}: no matching generator or job found in {os.getcwd()}")
            return 1
        editor(file)
        return 0


def find_file(testspec: str) -> str | None:
    """Return the source file path for *testspec* from the current workspace, or ``None``."""
    try:
        workspace = Workspace.load()
    except NotAWorkspaceError:
        return None
    spec = workspace.find(spec=testspec)
    return spec.file
