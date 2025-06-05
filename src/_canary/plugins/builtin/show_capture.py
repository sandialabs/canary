# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
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


class ShowLogAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        choices = ("all", "all:inline", "no", "stdout", "stdout:inline", "stderr", "stderr:inline")
        if values not in choices:
            parser.error(f"invalid capture choice, choose from {', '.join(choices)}")
        inline = False
        if values.endswith(":inline"):
            inline = True
            values = values.split(":")[0]
        setattr(namespace, self.dest, values)
        setattr(namespace, f"{self.dest}_inline", inline)


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--show-capture",
        command="run",
        dest="show_capture",
        action=ShowLogAction,
        metavar="{all, no, stdout, stderr}[:inline]",
        group="console reporting",
        default="no",
        help="Show captured stdout, stderr, or both (all) for failed tests.  If postfixed with "
        ":inline, the captured output is shown immediately, otherwise output is shown after all "
        "tests have complted [default: no]",
    )


@hookimpl(trylast=True)
def canary_session_finish(session: "Session", exitstatus: int) -> None:
    what, inline = config.getoption("show_capture"), config.getoption("show_capture_inline", False)
    if what in ("no", None):
        return
    elif inline:
        return
    cases = session.active_cases()
    failed = [case for case in cases if not case.status.satisfies(("success", "xdiff", "xfail"))]
    if failed:
        _, width = terminal_size()
        print(ccenter(colorize(" @*R{%d Test failures} " % len(failed)), width, "="), end="\n\n")
        for case in failed:
            show_capture(case, what=what)


@hookimpl(trylast=True)
def canary_testcase_finish(case: "TestCase", stage: str = "run") -> None:
    inline = config.getoption("show_capture_inline")
    if inline and not case.status.satisfies(("success", "xdiff", "xfail")):
        show_capture(case, what=config.getoption("show_capture"))


def show_capture(case: "TestCase", what: str = "all") -> None:
    _, width = terminal_size()
    color = "g" if case.status == "success" else "R" if case.status == "failed" else "y"
    fp = io.StringIO()
    fp.write(ccenter(colorize(" @*%s{%s} " % (color, case.display_name)), width, "-") + "\n")
    fp.write(f"{bold('Status')}: {case.status.cname}\n")
    fp.write(f"{bold('Execution directory')}: {case.execution_directory}\n")
    if what in ("stdout", "all"):
        if case.stdout_file:
            file = case.stdout_file
            if os.path.exists(file):
                with open(file) as fh:
                    stdout = fh.read().strip()
                if stdout:
                    fp.write(bold("Captured stdout") + "\n")
                    fp.write(indent(stdout, "  ") + "\n")
    if what in ("stderr", "all"):
        if case.stderr_file:
            file = case.stderr_file
            if os.path.exists(file):
                with open(file) as fh:
                    stderr = fh.read().strip()
                if stderr:
                    fp.write(bold("Captured stderr") + "\n")
                    fp.write(indent(stderr, "  ") + "\n")
    text = fp.getvalue()
    if text.strip():
        print(text)


def bold(string: str) -> str:
    return colorize("@*{%s}" % string)
