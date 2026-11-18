# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Job loading: the read side of the results database.

Loads jobs from the database with their results and dependencies resolved, and
finds jobs and specs by ID or pattern.  Building the jobs of a new session lives
in :mod:`_canary.engine.jobs`.
"""

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..core import jobspec
from ..core.execspace import ExecutionSpace
from ..core.job import Dependency
from ..core.job import Job
from ..util import logging

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..persistence.database import WorkspaceDatabase

logger = logging.get_logger(__name__)


class JobReconstructor:
    """Reconstructs Job objects from the database.

    This class handles:
    1. Loading jobs from database with latest results
    2. Job lookup/finding by ID or pattern
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
                lookup[spec.id] = job_from_result(self.sessions_dir, spec, deps, mine)
        if ids:
            return [job for job in lookup.values() if job.id in ids]
        return list(lookup.values())

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


def job_from_result(
    sessions_dir: Path, spec: "JobSpec", deps: list[Dependency], result: dict[str, Any]
) -> Job:
    """Rebuild a Job in the session that produced *result*, restored to that state."""
    space = ExecutionSpace(
        root=sessions_dir / result["session"],
        path=Path(result["workspace"]),
        session=result["session"],
    )
    job = Job(spec=spec, workspace=space, dependencies=deps)
    job.status = result["status"]
    job.state = result["state"]
    job.timekeeper = result["timekeeper"]
    job.measurements = result["measurements"]
    return job
