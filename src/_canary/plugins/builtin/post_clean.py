# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING

from ... import config
from ...hookspec import hookimpl
from ...workspace import Session
from ...workspace import Workspace

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--teardown",
        "--post-clean",
        command="run",
        action="store_true",
        default=None,
        help="Clean up files created by a test if it finishes successfully [default: %(default)s]",
    )


@hookimpl(trylast=True)
def canary_sessionfinish(session: "Session") -> None:
    if config.getoption("teardown"):
        workspace = Workspace.load()
        workspace.gc()
