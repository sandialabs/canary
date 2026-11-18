# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Build the jobs of a new session from specs and the workspace's latest results."""

from pathlib import Path
from typing import TYPE_CHECKING

from ..core.execspace import ExecutionSpace
from ..core.job import Dependency
from ..core.job import Job
from ..util import logging
from ..workspace.reconstruction import job_from_result

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..workspace.workspace import Workspace

logger = logging.get_logger(__name__)


def construct_jobs(workspace: "Workspace", specs: list["JobSpec"], session: Path) -> list["Job"]:
    """Create Job objects from specs, link to latest results if available.

    Args:
        workspace: Workspace whose database holds the latest results.
        specs: List of JobSpecs to convert to Jobs.
        session: Session path for new job execution.

    Returns:
        List of Job objects in dependency order.
    """
    from ..core.jobspec_graph import make_spec_graph

    lookup: dict[str, Job] = {}
    jobs: list[Job] = []
    latest = workspace.db.get_results([spec.id for spec in specs])
    graph = make_spec_graph(specs)
    for spec in graph.topo_order():
        deps = [Dependency(job=lookup[d.spec.id], when=d.when) for d in spec.dependencies]
        job: Job
        if spec.id in latest:
            job = job_from_result(workspace.sessions_dir, spec, deps, latest[spec.id])
        else:
            space = ExecutionSpace(root=session, path=spec.exec_path, session=session.name)
            job = Job(spec=spec, workspace=space, dependencies=deps)
        lookup[spec.id] = job
        jobs.append(job)
    return jobs


def refresh_masked_jobs(jobs: list[Job]) -> None:
    """Reload state of masked jobs from lock files.

    Nested canary processes (for example, ``canary hpc exec`` running inside
    a scheduler allocation) load upstream results from the workspace
    database, which only the top-level process writes, and it writes them
    asynchronously.  The lock file is written directly by whichever process
    ran the job, so it is the most current record of a job that this
    process will not run itself.  Jobs without a lock file are left as
    constructed.

    Args:
        jobs: Jobs constructed for this run.  Only masked jobs are refreshed.
    """
    for job in jobs:
        if not job.mask or not job.lockfile.exists():
            continue
        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh job %s from its lock file", job.id[:7], exc_info=True)
