# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import math
from collections import defaultdict
from graphlib import TopologicalSorter
from typing import Literal
from typing import cast

import canary

from .batchspec import BatchSpec
from .schedulepack import ScheduleTask
from .schedulepack import pack_by_count_atomic_simulated
from .schedulepack import pack_by_count_simulated
from .schedulepack import pack_to_height_simulated

logger = canary.get_logger(__name__)


PartitionCount = int | str | None


@dataclasses.dataclass(frozen=True)
class JobPartition:
    """A DAG-safe partition of jobs with a fixed simulation width."""

    jobs: list["canary.Job"]
    node_count: int
    cpus_per_node: int
    width: int
    key: str
    weight: float


def partition_jobs(
    *,
    jobs: list["canary.Job"],
    layout: Literal["flat", "atomic"],
    nodes: Literal["any", "same"],
    cpus_per_node: int,
) -> list[JobPartition]:
    """Partition jobs into DAG-safe groups with explicit schedule widths.

    Rules:

    - ``layout=flat,nodes=same``:
      partition by global topological level, then by actual required node count.

    - ``layout=flat,nodes=any``:
      partition by global topological level.  Width is based on the largest
      node count in that level.

    - ``layout=atomic,nodes=any``:
      return one partition containing all jobs.  Dependency-component packing is
      handled by ``batch_jobs``.

    - ``layout=atomic,nodes=same``:
      invalid.  Atomicity cannot generally be guaranteed while forcing
      dependency-connected jobs with different node counts into separate
      batches.
    """
    if cpus_per_node <= 0:
        raise ValueError(f"{cpus_per_node=} must be > 0")

    if layout not in ("flat", "atomic"):
        raise ValueError(f"invalid layout: {layout!r}")

    if nodes not in ("any", "same"):
        raise ValueError(f"invalid nodes value: {nodes!r}")

    if not jobs:
        return []

    _validate_unique_job_ids(jobs)

    if layout == "atomic":
        if nodes != "any":
            raise ValueError("layout=atomic requires nodes=any")

        node_count = max(_job_node_count(job) for job in jobs)
        width = node_count * cpus_per_node

        return [
            JobPartition(
                jobs=list(jobs),
                node_count=node_count,
                cpus_per_node=cpus_per_node,
                width=width,
                key=f"layout=atomic,nodes=any,node_count={node_count}",
                weight=_partition_weight(jobs, width=width),
            )
        ]

    partitions: list[JobPartition] = []

    for level_index, level_jobs in enumerate(_topological_job_levels(jobs)):
        if nodes == "same":
            by_node_count: dict[int, list[canary.Job]] = defaultdict(list)

            for job in level_jobs:
                by_node_count[_job_node_count(job)].append(job)

            for node_count in sorted(by_node_count):
                group = by_node_count[node_count]
                width = node_count * cpus_per_node

                partitions.append(
                    JobPartition(
                        jobs=group,
                        node_count=node_count,
                        cpus_per_node=cpus_per_node,
                        width=width,
                        key=(f"layout=flat,nodes=same,level={level_index},node_count={node_count}"),
                        weight=_partition_weight(group, width=width),
                    )
                )

        else:
            node_count = max(_job_node_count(job) for job in level_jobs)
            width = node_count * cpus_per_node

            partitions.append(
                JobPartition(
                    jobs=list(level_jobs),
                    node_count=node_count,
                    cpus_per_node=cpus_per_node,
                    width=width,
                    key=(f"layout=flat,nodes=any,level={level_index},node_count={node_count}"),
                    weight=_partition_weight(level_jobs, width=width),
                )
            )

    return partitions


def allocate_partition_counts(
    count: int | str | None, partitions: list[JobPartition]
) -> list[PartitionCount]:
    """Allocate a global count spec across DAG/resource partitions.

    Returns one count value per partition.

    Rules:

    - ``count is None``:
      duration-targeted batching.  Return ``None`` for each partition.

    - ``count == "max"``:
      return ``"max"`` for each partition.

    - ``count == N``:
      allocate at most ``N`` total count across partitions using a proportional
      allocation based on partition weight.

    Every non-empty partition needs at least one count.  Therefore, if integer
    ``count`` is smaller than the number of partitions, this function raises.
    """
    if not partitions:
        return []

    if count is None:
        return [None for _ in partitions]

    if count == "max":
        return ["max" for _ in partitions]

    if not isinstance(count, int):
        raise ValueError(f"invalid count value: {count!r}")

    if count <= 0:
        raise ValueError("count must be > 0")

    nparts = len(partitions)

    if count < nparts:
        raise ValueError(f"count={count} is insufficient for {nparts} DAG/resource partitions")

    capacities = [max(1, len(partition.jobs)) for partition in partitions]
    total_capacity = sum(capacities)
    budget = min(count, total_capacity)

    allocations: list[int] = [1 for _ in partitions]
    remaining = budget - nparts

    if remaining <= 0:
        return cast(list[PartitionCount], allocations)

    room = [capacity - 1 for capacity in capacities]

    weights = [max(float(partition.weight), 0.0) for partition in partitions]
    total_weight = sum(weights)

    if total_weight <= 0.0:
        weights = [float(len(partition.jobs)) for partition in partitions]
        total_weight = sum(weights)

    if total_weight <= 0.0:
        return cast(list[PartitionCount], allocations)

    quotas = [remaining * weight / total_weight for weight in weights]
    additions = [min(room[i], int(math.floor(quotas[i]))) for i in range(nparts)]

    for i, addition in enumerate(additions):
        allocations[i] += addition
        room[i] -= addition
        remaining -= addition

    order = sorted(
        range(nparts), key=lambda i: (quotas[i] - math.floor(quotas[i]), weights[i]), reverse=True
    )

    while remaining > 0:
        made_progress = False

        for i in order:
            if remaining <= 0:
                break

            if room[i] <= 0:
                continue

            allocations[i] += 1
            room[i] -= 1
            remaining -= 1
            made_progress = True

        if not made_progress:
            break

    return cast(list[PartitionCount], allocations)


def batch_jobs(
    *,
    jobs: list["canary.Job"],
    width: int,
    workers: int | None = None,
    nodes: Literal["any", "same"] = "same",
    layout: Literal["flat", "atomic"] = "flat",
    count: int | str | None = None,
    duration: float | None = None,
) -> list[BatchSpec]:
    """Partition jobs into simulated-scheduler batches.

    ``width`` is explicit and must be supplied by the caller.  For HPC usage it
    should usually be:

        node_count * cpus_per_node

    This function does not compute global batch dependencies.  If multiple
    partitions are batched independently, call ``set_batch_dependencies`` once
    on the combined list of returned ``BatchSpec`` objects.
    """
    if width <= 0:
        raise ValueError(f"{width=} must be > 0")

    if layout not in ("flat", "atomic"):
        raise ValueError(f"invalid layout: {layout!r}")

    if nodes not in ("any", "same"):
        raise ValueError(f"invalid nodes value: {nodes!r}")

    if duration is None and count is None:
        duration = 30 * 60  # 30 minute default

    if duration is not None and count is not None:
        raise ValueError("duration and count are mutually exclusive")

    if duration is not None and duration <= 0:
        raise ValueError("duration must be > 0")

    if duration is not None and layout == "atomic":
        raise ValueError("duration-targeted atomic layout is not supported")

    if layout == "atomic" and nodes != "any":
        raise ValueError("layout=atomic requires nodes=any")

    if not jobs:
        return []

    _validate_unique_job_ids(jobs)

    lookup: dict[str, canary.Job] = {job.id: job for job in jobs}
    tasks = [_schedule_task_from_job(job, lookup) for job in jobs]

    if duration is not None:
        logger.debug(
            "Batching jobs using simulated duration target=%s width=%s workers=%s",
            duration,
            width,
            workers,
        )

        scheduled_batches = pack_to_height_simulated(
            tasks, width=width, height=float(duration), workers=workers
        )

    else:
        count_value = _normalize_count(count, ntasks=len(tasks))

        logger.debug(
            "Batching jobs using simulated count=%s width=%s workers=%s layout=%s",
            count_value,
            width,
            workers,
            layout,
        )

        if layout == "atomic":
            scheduled_batches = pack_by_count_atomic_simulated(
                tasks, width=width, count=count_value, workers=workers
            )
        else:
            scheduled_batches = pack_by_count_simulated(
                tasks, width=width, count=count_value, workers=workers
            )

    specs: list[BatchSpec] = []

    for scheduled_batch in scheduled_batches:
        spec_jobs = [lookup[task.id] for task in scheduled_batch.tasks]
        spec = BatchSpec(
            layout=layout,
            jobs=spec_jobs,
            estimated_runtime=scheduled_batch.estimated_runtime,
            schedule_metadata={
                **dict(scheduled_batch.metadata),
                "estimated_runtime": scheduled_batch.estimated_runtime,
                "width": width,
                "workers": workers,
            },
        )

        # BatchSpec is not slotted, so attach simulation metadata directly.
        spec.estimated_runtime = scheduled_batch.estimated_runtime  # type: ignore[attr-defined]
        spec.schedule_metadata = dict(scheduled_batch.metadata)  # type: ignore[attr-defined]
        spec.schedule_metadata["estimated_runtime"] = scheduled_batch.estimated_runtime  # type: ignore[attr-defined]
        spec.schedule_metadata["width"] = width  # type: ignore[attr-defined]
        spec.schedule_metadata["workers"] = workers  # type: ignore[attr-defined]

        specs.append(spec)

    return specs


def set_batch_dependencies(specs: list[BatchSpec]) -> None:
    """Build explicit batch dependencies from child job dependencies.

    Call this after all partitions have been converted to ``BatchSpec`` objects.
    Calling this globally is important because dependencies may cross partition
    boundaries.
    """
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


def _schedule_task_from_job(job: "canary.Job", lookup: dict[str, "canary.Job"]) -> ScheduleTask:
    dependencies = tuple(dep.job.id for dep in job.dependencies if dep.job.id in lookup)

    try:
        priority = float(job.cost())
    except Exception:
        priority = None

    return ScheduleTask(
        id=job.id,
        width=max(1, int(job.cpus)),
        duration=float(math.ceil(job.runtime)),
        dependencies=dependencies,
        priority=priority,
        payload=job,
    )


def _normalize_count(count: int | str | None, *, ntasks: int) -> int:
    if count is None:
        raise ValueError("count is required when duration is not supplied")

    if count == "max":
        return max(ntasks, 1)

    if not isinstance(count, int):
        raise ValueError(f"invalid count value: {count!r}")

    if count <= 0:
        raise ValueError("count must be > 0")

    return count


def _validate_unique_job_ids(jobs: list["canary.Job"]) -> None:
    ids = [job.id for job in jobs]

    if len(set(ids)) != len(ids):
        duplicates = sorted({job_id for job_id in ids if ids.count(job_id) > 1})
        raise ValueError(f"Job ids must be unique; duplicates: {duplicates}")


def _job_node_count(job: "canary.Job") -> int:
    return max(1, len(job.required_resources()))


def _partition_weight(jobs: list["canary.Job"], *, width: int) -> float:
    """Return a simple estimated load for proportional count allocation."""
    if not jobs:
        return 0.0

    work = 0.0
    max_runtime = 0.0

    for job in jobs:
        runtime = float(math.ceil(job.runtime))
        cpus = max(1, int(job.cpus))

        work += cpus * runtime
        max_runtime = max(max_runtime, runtime)

    return max(max_runtime, work / max(width, 1))


def _topological_job_levels(jobs: list["canary.Job"]) -> list[list["canary.Job"]]:
    """Return global topological ready levels for jobs."""
    lookup: dict[str, canary.Job] = {job.id: job for job in jobs}
    job_ids = set(lookup)

    graph: dict[str, list[str]] = {}

    for job in jobs:
        graph[job.id] = [dep.job.id for dep in job.dependencies if dep.job.id in job_ids]

    ts = TopologicalSorter(graph)
    ts.prepare()

    levels: list[list[canary.Job]] = []

    while ts.is_active():
        ready_ids = list(ts.get_ready())
        ready_jobs = [lookup[job_id] for job_id in ready_ids]

        ready_jobs.sort(key=_job_priority_key, reverse=True)

        levels.append(ready_jobs)
        ts.done(*ready_ids)

    return levels


def _job_priority_key(job: "canary.Job") -> tuple[float, float, int, str]:
    try:
        cost = float(job.cost())
    except Exception:
        cost = math.sqrt(float(job.cpus) ** 2 + float(job.runtime) ** 2)

    return (cost, float(job.runtime), int(job.cpus), str(job.id))


class BatchNotFound(Exception):
    pass
