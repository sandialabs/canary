# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING

from ... import config
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...session import Session
    from ...test.case import TestCase


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
    if config.getoption("teardown"):
        cases = session.active_cases()
        for case in cases:
            teardown_if_ready(case)


@hookimpl(trylast=True)
def canary_testcase_finish(case: "TestCase") -> None:
    if config.getoption("teardown"):
        teardown_if_ready(case)


def teardown_if_ready(case: "TestCase") -> None:
    if all(_.status == "success" for _ in case.successors()) and case.status == "success":
        case.teardown()
