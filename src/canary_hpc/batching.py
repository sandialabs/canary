# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import math
from graphlib import TopologicalSorter
from typing import Iterable
from typing import Literal
from typing import Sequence

import canary
from _canary.util import cpu_count

from . import binpack
from .batchspec import BatchSpec

logger = canary.get_logger(__name__)


def batch_jobs(
    *,
    jobs: list["canary.Job"],
    nodes: Literal["any", "same"] = "same",
    layout: Literal["flat", "atomic"] = "flat",
    count: int | None = None,
    duration: float | None = None,
    width: int | None = None,
    cpus_per_node: int | None = None,
) -> list[BatchSpec]:
    if duration is None and count is None:
        duration = 30 * 60  # 30 minute default
    elif duration is not None and count is not None:
        raise ValueError("duration and count are mutually exclusive")

    bins: list[binpack.Bin] = []

    grouper: binpack.GrouperType | None = None
    if nodes == "same":
        grouper = GroupByNodes(cpus_per_node=cpus_per_node)
    # The binpacking code works with Block not Job.
    blocks: dict[str, binpack.Block] = {}
    lookup: dict[str, canary.Job] = {job.id: job for job in jobs}
    graph: dict[str, list[str]] = {}
    for job in jobs:
        graph[job.id] = [dep.job.id for dep in job.dependencies if dep.job.id in lookup]
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ready = ts.get_ready()
        for id in ready:
            job = lookup[id]
            assert job.id == id
            dependencies: list[binpack.Block] = []
            for dep in job.dependencies:
                if b := blocks.get(dep.job.id):
                    dependencies.append(b)
            blocks[job.id] = binpack.Block(
                job.id, job.cpus, math.ceil(job.runtime), dependencies=dependencies
            )
        ts.done(*ready)
    if duration is not None:
        height = math.ceil(float(duration))
        logger.debug(f"Batching jobs using duration={height}")
        bins = binpack.pack_to_height(
            list(blocks.values()), height=height, width=width, grouper=grouper
        )
    else:
        assert isinstance(count, int)
        logger.debug(f"Batching jobs using count={count}")
        if layout == "atomic":
            bins = binpack.pack_by_count_atomic(list(blocks.values()), count)
        else:
            bins = binpack.pack_by_count(list(blocks.values()), count, grouper=grouper)
    specs = [BatchSpec(layout=layout, jobs=[lookup[block.id] for block in bin]) for bin in bins]

    # Build explicit batch dependencies
    job_to_batch: dict[str, BatchSpec] = {}
    for spec in specs:
        for job in spec.jobs:
            job_to_batch[job.id] = spec

    for spec in specs:
        deps: list[BatchSpec] = []
        for job in spec.jobs:
            for dep in job.dependencies:
                dep_spec = job_to_batch.get(dep.job.id)
                if dep_spec is not None and dep_spec is not spec and dep_spec not in deps:
                    deps.append(dep_spec)
        spec.dependencies = deps

    return specs


def packed_perimeter(
    jobs: Iterable[canary.Job], cpus_per_node: int | None = None
) -> tuple[int, int]:
    cpus_per_node = cpus_per_node or cpu_count()
    jobs = sorted(jobs, key=lambda c: c.size(), reverse=True)
    cpus = max(job.cpus for job in jobs)
    nodes = math.ceil(cpus / cpus_per_node)
    width = nodes * cpus_per_node
    blocks: list[binpack.Block] = []
    for job in jobs:
        blocks.append(binpack.Block(job.id, job.cpus, math.ceil(job.runtime)))
    packer = binpack.Packer()
    packer.pack(blocks, width=width)
    return binpack.perimeter(blocks)


class GroupByNodes:
    def __init__(self, cpus_per_node: int | None) -> None:
        self.cpus_per_node: int = cpus_per_node or cpu_count()

    def __call__(self, blocks: Sequence[binpack.Block]) -> list[list[binpack.Block]]:
        groups: dict[int, list[binpack.Block]] = {}
        for block in blocks:
            nodes_reqd = math.ceil(block.width / self.cpus_per_node)
            groups.setdefault(nodes_reqd, []).append(block)
        return list(groups.values())


class BatchNotFound(Exception):
    pass
