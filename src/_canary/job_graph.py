# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Iterable
from typing import Sequence
from typing import TypeAlias

from .job import Job
from .util.level_graph import LevelGraph

JobGraph: TypeAlias = LevelGraph[Job]


def job_id(job: Job) -> str:
    return job.id


def job_dependencies(job: Job) -> Iterable[str]:
    for dep in job.dependencies:
        yield dep.job.id


def job_sort_key(job: Job) -> tuple[str, str]:
    name = getattr(job, "fullname", None) or getattr(job, "name", None) or job.id
    return str(name), job.id


def make_job_graph(jobs: Sequence[Job], *, require_closed: bool = True) -> JobGraph:
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
    return LevelGraph.from_levels(
        levels, id_fn=job_id, deps_fn=job_dependencies, require_closed=require_closed
    )
