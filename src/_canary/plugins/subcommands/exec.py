# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import datetime
import time
from typing import TYPE_CHECKING

import rich

from ... import config
from ...hookspec import hookimpl
from ...job import Job
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Exec())


class Exec(CanarySubcommand):
    name = "exec"
    description = "Execute a single job"

    def setup_parser(self, parser: "Parser") -> None:
        parser.set_defaults(banner=False)
        parser.add_argument("--session", help="Run the job in this session")
        parser.add_argument("spec", help="Run this spec ID")

    def execute(self, args: "argparse.Namespace") -> int:
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
        pm = config.pluginmanager.hook
        style = config.getoption("console_style") or {}
        namefmt = style.get("name", "short")
        display_name = job.display_name(style="rich", resolve=namefmt == "long")
        try:
            now = time.time()
            job.timekeeper.submitted = now
            rich.print(f"{display_name}: [blue]STARTING[/]")
            pm.canary_runteststart(case=job)
            now = time.time()
            job.timekeeper.started = now
            rich.print(f"{display_name}: [blue]RUNNING[/]")
            pm.canary_runtest(case=job)
            job.timekeeper.finished = time.time()
        finally:
            st = job.status.display_name(style="rich")
            rich.print(f"{display_name}: {st}")
            pm.canary_runtest_finish(case=job)
            job.save()
