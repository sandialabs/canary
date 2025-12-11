# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import io
import os
from textwrap import indent
from typing import TYPE_CHECKING

import rich

from ... import config
from ...hookspec import hookimpl
from ...util import logging
from ...util.term import terminal_size

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase
    from ...workspace import Session


logger = logging.get_logger(__name__)


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--show-capture",
        nargs="?",
        choices=("o", "e", "oe", "no"),
        group="console reporting",
        command="run",
        default="no",
        const="oe",
        help="Show captured stdout (o), stderr (e), or both (oe) "
        "for failed tests [default: %(default)s]",
    )


@hookimpl(specname="canary_session_finish", trylast=True)
def show_capture(session: "Session") -> None:
    what = config.getoption("show_capture")
    if what in ("no", None):
        return
    cases = session.cases
    failed = [case for case in cases if case.status.category == "FAIL"]
    if failed:
        _, width = terminal_size()
        string = f" {len(failed)} Test failures ".center(width, "=")
        rich.print(f"[bold red]{string}[/bold red]", end="\n\n")
        for case in failed:
            _show_capture(case, what=what)


def _show_capture(case: "TestCase", what="oe") -> None:
    _, width = terminal_size()
    fp = io.StringIO()
    fp.write("-" * width)
    fp.write(f"[bold]Status[/bold]: {case.status.display_name(style='rich')}\n")
    fp.write(f"[bold]Execution directory[/bold]: {case.workspace.dir}\n")
    command = case.get_attribute("command")
    fp.write(f"[bold]Command[/bold]: {command}\n")
    if what in ("o", "oe") and case.stdout:
        file = case.workspace.joinpath(case.stdout)
        if os.path.exists(file):
            with open(file) as fh:
                stdout = fh.read().strip()
            if stdout:
                fp.write("[bold]stdout[/bold]\n")
                fp.write(indent(stdout, "  ") + "\n")
    if what in ("e", "oe") and case.stderr:
        file = case.workspace.joinpath(case.stderr)
        if os.path.exists(file):
            with open(file) as fh:
                stderr = fh.read().strip()
            if stderr:
                fp.write("[bold]stderr[/bold]\n")
                fp.write(indent(stderr, "  ") + "\n")
    text = fp.getvalue()
    if text.strip():
        rich.print(text)
