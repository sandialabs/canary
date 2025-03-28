# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING

from ... import config
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...session import Session


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
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    if not config.getoption("teardown"):
        return
    cases = session.active_cases()
    for case in cases:
        if case.status == "success":
            case.teardown()
