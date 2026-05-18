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
    from ...job import Job
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


@hookimpl(specname="canary_sessionfinish", trylast=True)
def show_capture(session: "Session") -> None:
    what = config.getoption("show_capture")
    if what in ("no", None):
        return
    jobs = session.jobs
    failed = [job for job in jobs if job.status.is_failure()]
    if failed:
        _, width = terminal_size()
        string = f" {len(failed)} Test failures ".center(width, "=")
        rich.print(f"[bold red]{string}[/bold red]", end="\n\n")
        for job in failed:
            _show_capture(job, what=what)


def _show_capture(job: "Job", what="oe") -> None:
    _, width = terminal_size()
    fp = io.StringIO()
    fp.write("-" * width)
    fp.write(f"[bold]Status[/bold]: {job.status.display_name(style='rich')}\n")
    fp.write(f"[bold]Execution directory[/bold]: {job.workspace.dir}\n")
    command = job.get_attribute("command")
    fp.write(f"[bold]Command[/bold]: {command}\n")
    if what in ("o", "oe") and job.stdout:
        file = job.workspace.joinpath(job.stdout)
        if os.path.exists(file):
            with open(file) as fh:
                stdout = fh.read().strip()
            if stdout:
                fp.write("[bold]stdout[/bold]\n")
                fp.write(indent(stdout, "  ") + "\n")
    if what in ("e", "oe") and job.stderr:
        file = job.workspace.joinpath(job.stderr)
        if os.path.exists(file):
            with open(file) as fh:
                stderr = fh.read().strip()
            if stderr:
                fp.write("[bold]stderr[/bold]\n")
                fp.write(indent(stderr, "  ") + "\n")
    text = fp.getvalue()
    if text.strip():
        rich.print(text)
