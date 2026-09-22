# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary exec`` subcommand for running a single job directly."""

import argparse
import datetime
from typing import TYPE_CHECKING

import rich

from .. import config
from ..hookspec import hookimpl
from ..job import Job
from ..runtest import JobExecutor
from ..util import logging
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser

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
        """Resolve the spec, verify it is ready to run, execute it, and persist the result."""
        workspace = Workspace.load()
        now = datetime.datetime.now()
        session_name = args.session or now.isoformat(timespec="microseconds").replace(":", "-")
        session_dir = workspace.sessions_dir / session_name
        spec = workspace.find_jobspec(args.spec)
        specs = workspace.db.load_specs(ids=[spec.id], include_upstreams=True)
        jobs = workspace.construct_jobs(specs, session_dir)
        job: Job = next(j for j in jobs if j.id == spec.id)
        job.status.reset()
        job.state.reset()
        if job.is_ready():
            self.run_job(job)
            workspace.db.put_results(job)
        else:
            raise RuntimeError(f"{job}: job is not ready to run")
        return 0

    def run_job(self, job: Job) -> None:
        """Stage, run, and tear down *job*, printing live status updates.

        Delegates the phase orchestration to :class:`JobExecutor` so that hook
        exception handling and the final ``job.save()`` behave identically to
        the in-session scheduler.  A small event sink renders the live status
        lines from the executor's event stream.
        """
        style = config.getoption("console_style") or {}
        namefmt = style.get("name", "short")
        display_name = job.display_name(style="rich", resolve=namefmt == "long")

        sink = _StatusSink(job, display_name)
        JobExecutor()(job, sink)
        sink.print_final()


class _StatusSink:
    """Adapt :class:`JobExecutor` events to ``canary exec``'s live status lines.

    In the in-session scheduler these events drive job phase transitions via the
    executor's slot; here there is no slot, so this sink applies the same
    transitions to the job and renders the live status lines.
    """

    def __init__(self, job: Job, display_name: str) -> None:
        self.job = job
        self.display_name = display_name

    def put(self, event: dict) -> None:
        name = event.get("event")
        at = event.get("timestamp")
        if name == "job_submitted":
            self.job.on_submit(at=at)
        elif name == "job_staged":
            self.job.on_stage(at=at)
            rich.print(f"{self.display_name}: [blue]STARTING[/]")
        elif name == "job_started":
            self.job.on_start(at=at)
            rich.print(f"{self.display_name}: [blue]RUNNING[/]")
        elif name == "job_stopped":
            self.job.on_stop(at=at)

    def print_final(self) -> None:
        st = self.job.status.display_name(style="rich")
        rich.print(f"{self.display_name}: {st}")
