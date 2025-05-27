# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
from textwrap import indent
from typing import TYPE_CHECKING

from ... import config
from ...third_party.color import ccenter
from ...third_party.color import colorize
from ...util.term import terminal_size
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...session import Session


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--show-capture",
        command="run",
        group="console reporting",
        choices=("no", "stdout", "stderr", "all"),
        default="no",
        help="Controls how captured stdout/stderr is shown on failed tests [default: no]",
    )


@hookimpl(trylast=True)
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    show_capture = config.getoption("show_capture")
    if show_capture in ("no", None):
        return
    cases = session.active_cases()
    failed = [case for case in cases if not case.status.satisfies(("success", "xdiff", "xfail"))]
    if failed:
        _, width = terminal_size()
        print(bold(f"{len(failed)} Test failures:\n"))
        for case in failed:
            print(ccenter(colorize(" @*R{%s} " % (case.display_name)), width, "_"))
            print(f"{bold('Status')}: {case.status.cname}")
            print(f"{bold('Execution directory')}: {case.execution_directory}")
            if (stdout := case.stdout()) and show_capture in ("stdout", "all"):
                if os.path.exists(stdout):
                    print(bold("Captured stdout"))
                    print(indent(open(stdout).read().strip(), "  "))
            if (stderr := case.stderr()) and show_capture in ("stderr", "all"):
                if os.path.exists(stderr):
                    print(bold("Captured stderr"))
                    print(indent(open(stderr).read().strip(), "  "))
            print()
        print()


def bold(string: str) -> str:
    return colorize("@*{%s}" % string)
