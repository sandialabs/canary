# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Job reconstruction and loading.

This module handles converting JobSpecs to Job objects and loading jobs
from the database with their results and dependencies resolved.
"""

import fnmatch
import os
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..core import jobspec
from ..core.job import Dependency
from ..core.job import Job
from ..execution.testexec import ExecutionSpace
from ..util import logging

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..persistence.database import WorkspaceDatabase

logger = logging.get_logger(__name__)

_SESSION_DIR_VARIABLES = ("PYTHONPATH", "PATH")


class JobReconstructor:
    """Builds Job objects from JobSpecs and reconstructs from database.

    This class handles:
    1. Building Job objects from specs with dependency resolution
    2. Loading jobs from database with latest results
    3. Job lookup/finding by ID or pattern
    4. Refreshing masked jobs from lock files
    """

    def __init__(self, workspace_root: Path, sessions_dir: Path, db: "WorkspaceDatabase"):
        """Initialize job reconstructor.

        Args:
            workspace_root: Root path of the workspace.
            sessions_dir: Path to sessions directory.
            db: Workspace database for loading specs and results.
        """
        self.root = workspace_root
        self.sessions_dir = sessions_dir
        self.db = db

    def construct_jobs(self, specs: list["JobSpec"], session: Path) -> list["Job"]:
        """Create Job objects from specs, link to latest results if available.

        Args:
            specs: List of JobSpecs to convert to Jobs.
            session: Session path for new job execution.

        Returns:
            List of Job objects in dependency order.
        """
        from ..core.jobspec_graph import make_spec_graph

        lookup: dict[str, Job] = {}
        jobs: list[Job] = []
        latest = self.db.get_results([spec.id for spec in specs])
        graph = make_spec_graph(specs)
        for spec in graph.topo_order():
            deps = [Dependency(job=lookup[d.spec.id], when=d.when) for d in spec.dependencies]
            job: Job
            if spec.id in latest:
                mine = latest[spec.id]
                space = ExecutionSpace(
                    root=self.sessions_dir / mine["session"],
                    path=Path(mine["workspace"]),
                    session=mine["session"],
                )
                job = Job(spec=spec, workspace=space, dependencies=deps)
                job.status = mine["status"]
                job.state = mine["state"]
                job.timekeeper = mine["timekeeper"]
                job.measurements = mine["measurements"]
            else:
                space = ExecutionSpace(root=session, path=spec.exec_path, session=session.name)
                job = Job(spec=spec, workspace=space, dependencies=deps)
            lookup[spec.id] = job
            jobs.append(job)
        return jobs

    def load_jobs(self, ids: list[str] | None = None) -> list[Job]:
        """Load jobs from database with latest results.

        Args:
            ids: Optional list of specific job IDs to load.

        Returns:
            List of Job objects in static dependency order.
        """
        from ..core.jobspec_graph import make_spec_graph

        lookup: dict[str, Job] = {}
        latest = self.db.get_results(ids, include_upstreams=True)
        specs = self.db.load_specs(ids, include_upstreams=True)
        graph = make_spec_graph(specs)
        for spec in graph.topo_order():
            if mine := latest.get(spec.id):
                deps = [Dependency(job=lookup[d.spec.id], when=d.when) for d in spec.dependencies]
                space = ExecutionSpace(
                    root=self.sessions_dir / mine["session"],
                    path=Path(mine["workspace"]),
                    session=mine["session"],
                )
                job = Job(spec=spec, workspace=space, dependencies=deps)
                job.status = mine["status"]
                job.timekeeper = mine["timekeeper"]
                job.measurements = mine["measurements"]
                job.state = mine["state"]
                lookup[spec.id] = job
        if ids:
            return [job for job in lookup.values() if job.id in ids]
        return list(lookup.values())

    @staticmethod
    def refresh_masked_jobs(jobs: list["Job"]) -> None:
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
                logger.debug(
                    "Failed to refresh job %s from its lock file", job.id[:7], exc_info=True
                )

    def find(self, *, job: str | None = None, spec: str | None = None) -> Any:
        """Locate a Job or JobSpec in the workspace.

        Args:
            job: Identifier to find a Job.
            spec: Identifier to find a JobSpec.

        Returns:
            The found Job or JobSpec.
        """
        if (job is None) == (spec is None):
            raise TypeError("find() requires exactly one of job= or spec=")
        if job is not None:
            return self.find_job(job)
        assert spec is not None
        return self.find_jobspec(spec)

    def find_job(self, root: str) -> Job:
        """Locate Job by ID or matching pattern.

        Args:
            root: The ID or pattern to match.

        Returns:
            The matching Job object.

        Raises:
            ValueError: If no matching job is found.
        """
        id = self.db.resolve_spec_id(root)
        if id is not None:
            try:
                return self.load_jobs([id])[0]
            except IndexError as exc:
                raise ValueError(f"{id}: no matching test job found in {self.root}") from exc
        candidates: list[Job] = []
        jobs = self.load_jobs()
        for job in jobs:
            if job.spec.matches(root):
                return job
            elif job.spec.matches(root, fuzzy=True):
                candidates.append(job)
        if candidates:
            return candidates[0]
        raise ValueError(f"{root}: no matching test job found in {self.root}")

    def find_jobspec(self, root: str) -> "JobSpec":
        """Locate JobSpec by ID or matching pattern.

        Args:
            root: The ID or pattern to match.

        Returns:
            The matching JobSpec object.

        Raises:
            ValueError: If no matching spec is found.
        """
        id = self.db.resolve_spec_id(root)
        if id is not None:
            try:
                return self.db.load_specs([id])[0]
            except IndexError as exc:
                raise ValueError(f"{id}: no matching spec found in {self.root}") from exc
        specs = self.db.load_specs()
        for spec in specs:
            if spec.matches(root):
                return spec
        raise ValueError(f"{root}: no matching spec found in {self.root}")

    def find_specids(self, ids: list[str]) -> list[str | None]:
        """Resolve partial IDs or names to full spec IDs.

        Args:
            ids: List of strings to resolve.

        Returns:
            List of resolved spec IDs, or None if not found.
        """
        specs = self.db.load_specs()
        found: list[str | None] = []
        for id in ids:
            if id.startswith(jobspec.select_sygil):
                id = id[1:]
            for spec in specs:
                if spec.id.startswith(id):
                    found.append(spec.id)
                    break
                elif id in (spec.name, spec.display_name(), spec.display_name(resolve=True)):
                    found.append(spec.id)
                    break
                elif fnmatch.fnmatch(id, spec.name):
                    found.append(spec.id)
                    break
            else:
                found.append(None)
        return found

    @staticmethod
    def replace_session_dir_variables(job: "Job", *, old: Path, new: Path) -> None:
        """Replace session paths in environment variables.

        Args:
            job: The job whose variables to update.
            old: Old session directory path.
            new: New session directory path.
        """
        variables = job.variables
        old_s, new_s = str(old), str(new)
        for key in _SESSION_DIR_VARIABLES:
            value = variables.get(key)
            if not isinstance(value, str):
                continue
            if value == old_s:
                variables[key] = new_s
            elif value.startswith(old_s + os.pathsep):
                variables[key] = new_s + value[len(old_s) :]
