# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import io
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
    from ...test.case import TestCase


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--show-capture",
        command="run",
        group="console reporting",
        nargs="?",
        choices=("o", "e", "oe", "no"),
        default="no",
        const="oe",
        help="Show captured stdout (o), stderr (e), or both (oe) "
        "for failed tests [default: %(default)s]",
    )
    parser.add_argument(
        "--capture",
        command="run",
        choices=("log", "tee"),
        default="log",
        group="console reporting",
        help="Log test output to a file only (log) or log and print output "
        "to the screen (tee).  Warning: this could result in a large amount of text printed "
        "to the screen [default: log]",
    )


@hookimpl(trylast=True)
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    what = config.getoption("show_capture")
    if what in ("no", None):
        return
    cases = session.active_cases()
    failed = [
        case for case in cases if not case.status.satisfies(("success", "xdiff", "xfail"))
    ]
    if failed:
        _, width = terminal_size()
        print(
            ccenter(colorize(" @*R{%d Test failures} " % len(failed)), width, "="), end="\n\n"
        )
        for case in failed:
            show_capture(case, what=what)


def show_capture(case: "TestCase", what="oe") -> None:
    _, width = terminal_size()
    color = "g" if case.status == "success" else "R" if case.status == "failed" else "y"
    fp = io.StringIO()
    fp.write(ccenter(colorize(" @*%s{%s} " % (color, case.display_name)), width, "-") + "\n")
    fp.write(f"{bold('Status')}: {case.status.cname}\n")
    fp.write(f"{bold('Execution directory')}: {case.execution_directory}\n")
    fp.write(f"{bold('Command')}: {' '.join(case.command())}\n")
    if what in ("o", "oe") and case.stdout_file:
        file = case.stdout_file
        if os.path.exists(file):
            with open(file) as fh:
                stdout = fh.read().strip()
            if stdout:
                fp.write(bold("stdout") + "\n")
                fp.write(indent(stdout, "  ") + "\n")
    if what in ("e", "oe") and case.stderr_file:
        file = case.stderr_file
        if os.path.exists(file):
            with open(file) as fh:
                stderr = fh.read().strip()
            if stderr:
                fp.write(bold("stderr") + "\n")
                fp.write(indent(stderr, "  ") + "\n")
    text = fp.getvalue()
    if text.strip():
        print(text)


def bold(string: str) -> str:
    return colorize("@*{%s}" % string)
