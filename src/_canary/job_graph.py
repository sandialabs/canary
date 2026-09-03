# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Dependency graph construction helpers for :class:`~_canary.job.Job` objects.

Wraps :class:`~_canary.util.level_graph.LevelGraph` with job-specific ID and
dependency accessor functions.  The resulting ``JobGraph`` is used by the
executor to determine dispatch order and to propagate blocked status from
failed dependencies.
"""

from typing import Iterable
from typing import Sequence
from typing import TypeAlias

from .job import Job
from .util.level_graph import LevelGraph

JobGraph: TypeAlias = LevelGraph[Job]


def job_id(job: Job) -> str:
    """Return the unique string ID for *job* (used as the graph node key)."""
    return job.id


def job_dependencies(job: Job) -> Iterable[str]:
    """Yield the IDs of all jobs that *job* depends on."""
    for dep in job.dependencies:
        yield dep.job.id


def job_sort_key(job: Job) -> tuple[str, str]:
    """Return a stable sort key for *job* used to order nodes at the same level.

    Prefers ``fullname`` over ``name`` over ``id`` for human-readable ordering.
    """
    name = getattr(job, "fullname", None) or getattr(job, "name", None) or job.id
    return str(name), job.id


def make_job_graph(jobs: Sequence[Job], *, require_closed: bool = True) -> JobGraph:
    """Build a dependency graph from a flat sequence of :class:`~_canary.job.Job` objects.

    Args:
        jobs: All jobs to include in the graph.
        require_closed: If ``True`` (default), raise an error if any dependency
            reference points to a job not present in *jobs*.

    Returns:
        A :class:`~_canary.util.level_graph.LevelGraph` of jobs in topological
        order.
    """
    return LevelGraph.from_items(
        jobs,
        id_fn=job_id,
        deps_fn=job_dependencies,
        sort_key=job_sort_key,
        require_closed=require_closed,
    )


def make_job_graph_from_levels(
    levels: Sequence[Sequence[Job]], *, require_closed: bool = True
) -> JobGraph:
    """Build a dependency graph from an already-levelled sequence of job groups.

    Args:
        levels: Sequence of job groups where level *n* contains jobs that may
            depend on jobs at level *n-1*.
        require_closed: If ``True`` (default), raise an error for unresolved
            dependency references.

    Returns:
        A :class:`~_canary.util.level_graph.LevelGraph` of jobs.
    """
    return LevelGraph.from_levels(
        levels, id_fn=job_id, deps_fn=job_dependencies, require_closed=require_closed
    )
