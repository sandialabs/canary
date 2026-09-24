# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary exec`` subcommand for running a single job directly."""

import argparse
from typing import TYPE_CHECKING

import rich

from .. import app
from .. import config
from ..hookspec import hookimpl
from ..util import logging
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..job import Job

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Exec())


class Exec(CanarySubcommand):
    """Execute a single job spec by ID, bypassing the normal session scheduler."""

    name = "exec"
    description = "Execute a single job"

    def setup_parser(self, parser: "Parser") -> None:
        """Register the ``spec`` positional ID and optional ``--session`` arguments."""
        parser.set_defaults(banner=False)
        parser.add_argument("--session", help="Run the job in this session")
        parser.add_argument("spec", help="Run this spec ID")

    def execute(self, args: "argparse.Namespace") -> int:
        """Run the requested job through the app, rendering its live status."""
        renderer = _StatusRenderer()
        job = app.exec_job(args.spec, session=args.session, observer=renderer)
        renderer.print_final(job)
        return 0


class _StatusRenderer:
    """Render ``canary exec``'s live status lines from executor events.

    The application layer applies the job's phase transitions; this observer
    only reacts to events for display.  The job's display name is resolved lazily
    on the first rendered event so it reflects the current console style.
    """

    def __init__(self) -> None:
        self._display_name: str | None = None

    def __call__(self, event: dict) -> None:
        name = event.get("event")
        job = event.get("job")
        if name == "job_staged" and job is not None:
            rich.print(f"{self._name(job)}: [blue]STARTING[/]")
        elif name == "job_started" and job is not None:
            rich.print(f"{self._name(job)}: [blue]RUNNING[/]")

    def print_final(self, job: "Job") -> None:
        status = job.status.display_name(style="rich")
        rich.print(f"{self._name(job)}: {status}")

    def _name(self, job: "Job") -> str:
        if self._display_name is None:
            style = config.getoption("console_style") or {}
            resolve = style.get("name", "short") == "long"
            self._display_name = job.display_name(style="rich", resolve=resolve)
        return self._display_name
