# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import math
from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from typing import Literal
from typing import cast

import canary

from .batchspec import BatchSpec
from .schedulepack import ScheduleTask
from .schedulepack import node_demand_from_request
from .schedulepack import pack_by_count_atomic_simulated
from .schedulepack import pack_by_count_simulated
from .schedulepack import pack_to_height_simulated

logger = canary.get_logger(__name__)


PartitionCount = int | None
BatchLayout = Literal["flat", "atomic"]
NodePolicy = Literal["same", "any"]
MAX_COUNT = -1


@dataclasses.dataclass(frozen=True, slots=True)
class DurationTarget:
    seconds: float

    def __post_init__(self) -> None:
        if isinstance(self.seconds, bool) or not isinstance(self.seconds, (int, float)):
            raise TypeError(f"duration must be numeric, got {type(self.seconds).__name__}")
        if self.seconds <= 0:
            raise ValueError(f"duration must be > 0, got {self.seconds!r}")

    def __serialize__(self) -> dict[str, Any]:
        return {"seconds": self.seconds}

    @classmethod
    def __deserialize__(cls, arg: dict[str, Any]) -> "DurationTarget":
        return DurationTarget(seconds=float(arg["seconds"]))


@dataclasses.dataclass(frozen=True, slots=True)
class CountTarget:
    """Batch by count.

    ``count == MAX_COUNT`` means "maximum number of batches".
    """

    count: int

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or not isinstance(self.count, int):
            raise TypeError(f"count must be an integer, got {self.count!r}")
        if self.count == MAX_COUNT:
            return
        if self.count <= 0:
            raise ValueError(f"count must be > 0 or MAX_COUNT, got {self.count!r}")

    def __serialize__(self) -> dict[str, Any]:
        return {"count": self.count}

    @classmethod
    def __deserialize__(cls, arg: dict[str, Any]) -> "CountTarget":
        return CountTarget(count=int(arg["count"]))

    @classmethod
    def max(cls) -> "CountTarget":
        return cls(MAX_COUNT)


BatchTarget = DurationTarget | CountTarget


@dataclasses.dataclass(frozen=True, slots=True)
class BatchingSpec:
    layout: BatchLayout
    node_policy: NodePolicy
    target: BatchTarget

    def __post_init__(self) -> None:
        if self.layout not in ("flat", "atomic"):
            raise ValueError(f"batch spec: invalid layout value {self.layout!r}")

        if self.node_policy not in ("same", "any"):
            raise ValueError(f"batch spec: invalid nodes value {self.node_policy!r}")

        if self.layout == "atomic" and self.node_policy != "any":
            raise ValueError("batch spec: layout=atomic requires nodes=any")

        if self.layout == "atomic" and isinstance(self.target, DurationTarget):
            raise ValueError("batch spec: duration-targeted atomic layout is not supported")

    def __serialize__(self) -> dict[str, Any]:
        return {"layout": self.layout, "node_policy": self.node_policy, "target": self.target}

    @classmethod
    def __deserialize__(cls, arg: dict[str, Any]) -> "BatchingSpec":
        return BatchingSpec(
            layout=arg["layout"], node_policy=arg["node_policy"], target=arg["target"]
        )

    @classmethod
    def with_defaults(
        cls,
        *,
        nodes: NodePolicy | None = None,
        layout: BatchLayout | None = None,
        count: int | Literal["max"] | None = None,
        duration: float | None = None,
    ) -> "BatchingSpec":
        """Create a validated batching spec from parser-style fields.

        ``count='max'`` is normalized to ``CountTarget(MAX_COUNT)``.
        """
        resolved_layout: BatchLayout = layout or "flat"

        if nodes is None:
            resolved_nodes: NodePolicy = "any" if resolved_layout == "atomic" else "same"
        else:
            resolved_nodes = nodes

        if count is not None and duration is not None:
            raise ValueError("batch spec: duration not allowed with count")

        if count is not None:
            target: BatchTarget
            if count == "max":
                target = CountTarget.max()
            else:
                target = CountTarget(count)
        elif duration is not None:
            target = DurationTarget(float(duration))
        elif resolved_layout == "atomic":
            target = CountTarget.max()
        else:
            target = DurationTarget(30 * 60.0)

        return cls(layout=resolved_layout, node_policy=resolved_nodes, target=target)

    @property
    def nodes(self) -> NodePolicy:
        """Parser-compatible alias for ``node_policy``."""
        return self.node_policy

    @property
    def count(self) -> int | None:
        if isinstance(self.target, CountTarget):
            return self.target.count
        return None

    @property
    def duration(self) -> float | None:
        if isinstance(self.target, DurationTarget):
            return self.target.seconds
        return None

    def count_is_max(self) -> bool:
        return self.count == MAX_COUNT


@dataclasses.dataclass(frozen=True)
class JobPartition:
    """A DAG-safe partition of jobs with a fixed simulation width."""

    jobs: list["canary.Job"]
    node_count: int
    cpus_per_node: int
    width: int
    resource_capacity: dict[str, int]
    key: str
    weight: float


def partition_jobs(
    *,
    jobs: list["canary.Job"],
    layout: Literal["flat", "atomic"],
    nodes: Literal["any", "same"],
    cpus_per_node: int,
    resources_per_node: dict[str, int] | None = None,
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

    if resources_per_node is not None:
        resources_per_node = dict(resources_per_node)
        resources_per_node["cpus"] = cpus_per_node

        for rtype, count in resources_per_node.items():
            if int(count) < 0:
                raise ValueError(f"resources_per_node[{rtype!r}] must be >= 0")

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
        group = list(jobs)
        resource_capacity = _partition_resource_capacity(
            group, width=width, node_count=node_count, resources_per_node=resources_per_node
        )
        return [
            JobPartition(
                jobs=group,
                node_count=node_count,
                cpus_per_node=cpus_per_node,
                width=width,
                resource_capacity=resource_capacity,
                key=f"layout=atomic,nodes=any,node_count={node_count}",
                weight=_partition_weight(group, width=width),
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
                resource_capacity = _partition_resource_capacity(
                    group, width=width, node_count=node_count, resources_per_node=resources_per_node
                )
                partitions.append(
                    JobPartition(
                        jobs=group,
                        node_count=node_count,
                        cpus_per_node=cpus_per_node,
                        width=width,
                        key=(f"layout=flat,nodes=same,level={level_index},node_count={node_count}"),
                        weight=_partition_weight(group, width=width),
                        resource_capacity=resource_capacity,
                    )
                )

        else:
            node_count = max(_job_node_count(job) for job in level_jobs)
            width = node_count * cpus_per_node
            group = list(level_jobs)
            resource_capacity = _partition_resource_capacity(
                group, width=width, node_count=node_count, resources_per_node=resources_per_node
            )
            partitions.append(
                JobPartition(
                    jobs=group,
                    node_count=node_count,
                    cpus_per_node=cpus_per_node,
                    width=width,
                    resource_capacity=resource_capacity,
                    key=(f"layout=flat,nodes=any,level={level_index},node_count={node_count}"),
                    weight=_partition_weight(group, width=width),
                )
            )

    return partitions


def allocate_partition_counts(
    count: int | None, partitions: list[JobPartition]
) -> list[int | None]:
    if not partitions:
        return []

    if count is None:
        return [None for _ in partitions]

    if count == MAX_COUNT:
        return [MAX_COUNT for _ in partitions]

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
    spec: BatchingSpec,
    resource_capacity: dict[str, int] | None = None,
    node_count: int | None = None,
    exact_final_estimate: bool = False,
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

    if resource_capacity is not None:
        resource_capacity = dict(resource_capacity)
        resource_capacity.setdefault("cpus", int(width))

        for rtype, capacity in resource_capacity.items():
            if int(capacity) <= 0:
                raise ValueError(f"resource capacity for {rtype!r} must be > 0")

    if node_count is not None and node_count <= 0:
        raise ValueError(f"{node_count=} must be > 0")

    if not jobs:
        return []

    _validate_unique_job_ids(jobs)

    lookup: dict[str, canary.Job] = {job.id: job for job in jobs}
    tasks = [_schedule_task_from_job(job, lookup) for job in jobs]

    if isinstance(spec.target, DurationTarget):
        logger.debug(
            "Batching jobs using simulated duration target=%s width=%s workers=%s",
            spec.target.seconds,
            width,
            workers,
        )

        scheduled_batches = pack_to_height_simulated(
            tasks,
            width=width,
            height=spec.target.seconds,
            workers=workers,
            resource_capacity=resource_capacity,
            node_count=node_count,
            exact_final_estimate=exact_final_estimate,
        )

    else:
        assert isinstance(spec.target, CountTarget)
        count_value = _normalize_count(spec.target.count, ntasks=len(tasks))
        logger.debug(
            "Batching jobs using simulated count=%s width=%s workers=%s layout=%s",
            count_value,
            width,
            workers,
            spec.layout,
        )

        if spec.layout == "atomic":
            scheduled_batches = pack_by_count_atomic_simulated(
                tasks,
                width=width,
                count=count_value,
                workers=workers,
                resource_capacity=resource_capacity,
                node_count=node_count,
                exact_final_estimate=exact_final_estimate,
            )
        else:
            scheduled_batches = pack_by_count_simulated(
                tasks,
                width=width,
                count=count_value,
                workers=workers,
                resource_capacity=resource_capacity,
                node_count=node_count,
                exact_final_estimate=exact_final_estimate,
            )

    batchspecs: list[BatchSpec] = []

    for scheduled_batch in scheduled_batches:
        spec_jobs = [lookup[task.id] for task in scheduled_batch.tasks]
        batchspec = BatchSpec(
            layout=spec.layout,
            jobs=spec_jobs,
            estimated_runtime=scheduled_batch.estimated_runtime,
            schedule_metadata={
                **dict(scheduled_batch.metadata),
                "estimated_runtime": scheduled_batch.estimated_runtime,
                "width": width,
                "workers": workers,
                "resource_capacity": dict(resource_capacity)
                if resource_capacity is not None
                else None,
                "node_count": node_count,
                "exact_final_estimate": exact_final_estimate,
            },
        )
        batchspecs.append(batchspec)

    return batchspecs


def normalize_batching_spec(batchspec: BatchingSpec | Mapping[str, Any] | None) -> BatchingSpec:
    if isinstance(batchspec, BatchingSpec):
        return batchspec
    if batchspec is None:
        return BatchingSpec.with_defaults()
    return BatchingSpec.with_defaults(**batchspec)


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

    requests = job.required_resources()
    demands = tuple(node_demand_from_request(request) for request in requests)

    return ScheduleTask(
        id=job.id,
        width=max(1, int(job.cpus)),
        duration=float(math.ceil(job.runtime)),
        dependencies=dependencies,
        priority=priority,
        payload=job,
        demands=demands,
    )


def _normalize_count(count: int, *, ntasks: int) -> int:
    if count <= 0:
        return max(ntasks, 1)
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


def _partition_resource_capacity(
    jobs: list["canary.Job"],
    *,
    width: int,
    node_count: int,
    resources_per_node: dict[str, int] | None = None,
) -> dict[str, int]:
    """Return a transition resource-capacity vector for a partition.

    CPU capacity is the scalar simulation width.  Other resource capacities are
    conservatively inferred as the maximum total demand of any single job in the
    partition.

    This keeps batching resource-aware without requiring backend resource
    capacity plumbing yet.
    """
    capacity: dict[str, int] = {"cpus": int(width)}

    if resources_per_node is not None:
        for rtype, per_node_count in resources_per_node.items():
            total = int(per_node_count) * int(node_count)
            if total > 0:
                if rtype in ("cpu", "cpus"):
                    capacity["cpus"] = int(width)
                else:
                    capacity[rtype] = total
        return capacity

    # Transition fallback: infer non-CPU capacity from the maximum single-job
    # demand in the partition.
    for job in jobs:
        totals: dict[str, int] = {}

        for request in job.required_resources():
            for item in request.resources:
                rtype = str(item["type"])
                slots = int(item.get("slots", 1))

                if slots <= 0:
                    continue

                if rtype in ("cpu", "cpus"):
                    continue

                totals[rtype] = totals.get(rtype, 0) + slots

        for rtype, slots in totals.items():
            capacity[rtype] = max(capacity.get(rtype, 0), slots)

    return capacity


def _topological_job_levels(jobs: list["canary.Job"]) -> list[list["canary.Job"]]:
    """Return global topological ready levels for jobs."""
    from _canary.job_graph import make_job_graph

    graph = make_job_graph(jobs)
    return [list(level) for level in graph.levels]


class BatchNotFound(Exception):
    pass
