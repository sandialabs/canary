# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Simulation-based schedule packing utilities.

This module partitions schedulable tasks into batches by repeatedly estimating
how a simple priority/resource scheduler would execute each candidate batch.

The scheduler model is:

- tasks become runnable after their in-batch dependencies complete;
- runnable tasks are considered in descending priority order;
- the first task that fits the remaining width is started;
- at most ``workers`` tasks may run simultaneously;
- time advances to the next task completion;
- resources are released and the process repeats.

The packers in this module intentionally require an explicit ``width``.  They
do not infer machine width or resource capacity.
"""

from __future__ import annotations

import dataclasses
import heapq
import math
from collections import Counter
from graphlib import TopologicalSorter
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Iterator
from typing import Sequence


@dataclasses.dataclass(frozen=True, slots=True)
class ScheduleTask:
    """A schedulable task.

    Parameters
    ----------
    id:
        Stable task identifier.

    width:
        Scalar resource demand.  For Canary HPC batching this is typically CPU
        count, but the scheduler only treats it as an abstract width.

    duration:
        Estimated task runtime in seconds.

    dependencies:
        IDs of tasks that must complete before this task can start.  Dependency
        IDs outside the current simulation set are ignored by the simulator and
        treated as already satisfied.

    priority:
        Optional explicit scheduling priority.  Higher priority tasks are
        considered first.  If omitted, ``default_priority()`` is used.

    payload:
        Optional caller-owned object.  An interface layer may store the original
        job object here.
    """

    id: str
    width: int
    duration: float
    dependencies: tuple[str, ...] = ()
    priority: float | None = None
    payload: Any = dataclasses.field(default=None, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ScheduleTask.id must be non-empty")
        if self.width <= 0:
            raise ValueError(f"ScheduleTask {self.id!r}: width must be > 0")
        if self.duration < 0:
            raise ValueError(f"ScheduleTask {self.id!r}: duration must be >= 0")
        object.__setattr__(self, "dependencies", tuple(self.dependencies))

    def default_priority(self) -> float:
        """Return a default priority based on resource size and duration."""
        return math.sqrt(float(self.width) ** 2 + float(self.duration) ** 2)

    def scheduling_priority(self) -> float:
        """Return the priority used by the scheduler simulation."""
        if self.priority is not None:
            return float(self.priority)
        return self.default_priority()

    def work(self) -> float:
        """Return scalar resource-time work."""
        return float(self.width) * float(self.duration)


@dataclasses.dataclass(slots=True)
class ScheduledBatch:
    """A batch returned by the simulation-based packers."""

    tasks: list[ScheduleTask]
    estimated_runtime: float = 0.0
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def __iter__(self) -> Iterator[ScheduleTask]:
        return iter(self.tasks)

    def __len__(self) -> int:
        return len(self.tasks)

    def __bool__(self) -> bool:
        return bool(self.tasks)

    def __repr__(self) -> str:
        return (
            f"ScheduledBatch(n={len(self.tasks)}, estimated_runtime={self.estimated_runtime:.1f})"
        )

    @property
    def ids(self) -> list[str]:
        return [task.id for task in self.tasks]

    @property
    def total_width(self) -> int:
        return sum(task.width for task in self.tasks)

    @property
    def total_duration(self) -> float:
        return sum(task.duration for task in self.tasks)

    @property
    def total_work(self) -> float:
        return sum(task.work() for task in self.tasks)

    def recompute_runtime(self, estimator: Callable[[list[ScheduleTask]], float]) -> None:
        self.estimated_runtime = estimator(self.tasks)


def pack_to_height_simulated(
    tasks: Sequence[ScheduleTask], *, width: int, height: float, workers: int | None = None
) -> list[ScheduledBatch]:
    """Pack tasks into duration-targeted batches.

    This is a flat-layout packer.

    The algorithm is:

    1. Split the dependency graph into topological ready levels.
    2. Within each level, use best-fit decreasing placement.
    3. Score every candidate placement by scheduler simulation.
    4. Prefer the feasible batch whose simulated runtime leaves the least slack
       under ``height``.
    5. Open a new batch when no existing batch can accept the task.

    Dependencies between returned batches can be reconstructed by the caller
    from the original task dependency graph.

    A task whose own simulated runtime exceeds ``height`` is placed into an
    over-target batch rather than being dropped.
    """
    task_list = _validate_tasks(tasks, width=width)

    if height <= 0:
        raise ValueError(f"{height=} must be > 0")

    batches: list[ScheduledBatch] = []

    for level in _topological_levels(task_list):
        units = [[task] for task in level]
        batches.extend(
            _best_fit_by_simulated_height(
                units,
                width=width,
                height=height,
                workers=workers,
                metadata={
                    "algorithm": "pack_to_height_simulated",
                    "layout": "flat",
                    "target_height": height,
                    "width": width,
                    "workers": workers,
                },
            )
        )

    return batches


def pack_by_count_simulated(
    tasks: Sequence[ScheduleTask], *, width: int, count: int, workers: int | None = None
) -> list[ScheduledBatch]:
    """Pack tasks into at most ``count`` flat-layout batches.

    The algorithm is:

    1. Split the dependency graph into topological ready levels.
    2. Create one batch per level.
    3. If additional batches are available, repeatedly split the currently
       longest estimated batch.
    4. Each split is performed by greedy least-makespan assignment using the
       same scheduler simulation.

    Because this is a flat-layout packer, ``count`` must be at least the number
    of topological ready levels.
    """
    task_list = _validate_tasks(tasks, width=width)

    if count <= 0:
        raise ValueError(f"{count=} must be > 0")

    if not task_list:
        return []

    # Explicit "max-like" behavior: if the caller gives enough count for one
    # batch per task, honor that.  This preserves count=max semantics after the
    # interface layer normalizes count=max to len(tasks).
    if count >= len(task_list):
        return [
            _make_batch(
                [task],
                width=width,
                workers=workers,
                metadata={
                    "algorithm": "pack_by_count_simulated",
                    "layout": "flat",
                    "width": width,
                    "workers": workers,
                    "count": count,
                    "mode": "one_task_per_batch",
                },
            )
            for task in sorted(task_list, key=_priority_key, reverse=True)
        ]

    levels = _topological_levels(task_list)

    if len(levels) > count:
        raise ValueError(
            f"{count=} insufficient for flat layout; "
            f"dependency graph requires at least {len(levels)} level batches"
        )

    batches = [
        _make_batch(
            level,
            width=width,
            workers=workers,
            metadata={
                "algorithm": "pack_by_count_simulated",
                "layout": "flat",
                "width": width,
                "workers": workers,
                "count": count,
            },
        )
        for level in levels
    ]

    while len(batches) < count:
        splittable = [(index, batch) for index, batch in enumerate(batches) if len(batch.tasks) > 1]

        if not splittable:
            break

        index, batch = max(splittable, key=lambda item: item[1].estimated_runtime)

        split = _partition_units_by_count(
            [[task] for task in batch.tasks],
            count=2,
            width=width,
            workers=workers,
            metadata={
                "algorithm": "pack_by_count_simulated",
                "layout": "flat",
                "width": width,
                "workers": workers,
                "count": count,
            },
        )

        if len(split) <= 1:
            break

        batches[index : index + 1] = split

    return [batch for batch in batches if batch]


def pack_by_count_atomic_simulated(
    tasks: Sequence[ScheduleTask], *, width: int, count: int, workers: int | None = None
) -> list[ScheduledBatch]:
    """Pack tasks into at most ``count`` atomic-layout batches.

    The algorithm is:

    1. Compute dependency-connected components, ignoring edge direction.
    2. Treat each component as an indivisible placement unit.
    3. Assign components to batches using greedy least-makespan placement.
    4. Score each candidate placement by scheduler simulation.

    The resulting batches may contain internal dependencies, but dependency-
    connected tasks are kept together.
    """
    task_list = _validate_tasks(tasks, width=width)

    if count <= 0:
        raise ValueError(f"{count=} must be > 0")

    components = _dependency_components(task_list)

    if not components:
        return []

    return _partition_units_by_count(
        components,
        count=min(count, len(components)),
        width=width,
        workers=workers,
        metadata={
            "algorithm": "pack_by_count_atomic_simulated",
            "layout": "atomic",
            "width": width,
            "workers": workers,
        },
    )


def simulate_makespan(
    tasks: Sequence[ScheduleTask], *, width: int, workers: int | None = None
) -> float:
    """Estimate task-set runtime using a priority/resource scheduler simulation.

    The simulation uses a scalar resource capacity ``width`` and optional worker
    limit ``workers``.

    Dependencies whose IDs are not present in ``tasks`` are ignored and treated
    as already satisfied.
    """
    task_list = _validate_tasks(tasks, width=width)

    if not task_list:
        return 0.0

    task_by_id = {task.id: task for task in task_list}
    task_ids = set(task_by_id)

    dependencies: dict[str, set[str]] = {
        task.id: {dep for dep in task.dependencies if dep in task_ids} for task in task_list
    }

    pending: set[str] = set(task_ids)
    complete: set[str] = set()

    # Heap entries are:
    #   finish_time, sequence_number, task_id
    running: list[tuple[float, int, str]] = []

    now = 0.0
    used_width = 0
    seq = 0
    max_workers = _effective_workers(workers, len(task_list))

    while pending or running:
        made_progress = False

        while len(running) < max_workers:
            ready = [
                task_by_id[task_id]
                for task_id in pending
                if dependencies[task_id].issubset(complete)
            ]

            if not ready:
                break

            ready.sort(key=_priority_key, reverse=True)

            selected: ScheduleTask | None = None

            for task in ready:
                if used_width + task.width <= width:
                    selected = task
                    break

            if selected is None:
                break

            pending.remove(selected.id)
            used_width += selected.width

            finish_time = now + float(selected.duration)
            heapq.heappush(running, (finish_time, seq, selected.id))
            seq += 1
            made_progress = True

        if running:
            finish_time, _, finished_id = heapq.heappop(running)
            now = finish_time

            finished_ids = [finished_id]

            while running and running[0][0] == finish_time:
                _, _, also_finished_id = heapq.heappop(running)
                finished_ids.append(also_finished_id)

            for task_id in finished_ids:
                task = task_by_id[task_id]
                used_width -= task.width
                complete.add(task_id)

            continue

        if pending and not made_progress:
            ready_ids = [task_id for task_id in pending if dependencies[task_id].issubset(complete)]

            if not ready_ids:
                raise ValueError("Dependency cycle detected among scheduled tasks")

            impossible = [
                task_by_id[task_id] for task_id in ready_ids if task_by_id[task_id].width > width
            ]

            if impossible:
                details = ", ".join(f"{task.id}:width={task.width}" for task in impossible)
                raise ValueError(f"Tasks exceed available {width=}: {details}")

            raise RuntimeError("Scheduler simulation made no progress")

    return now


def _make_batch(
    tasks: Sequence[ScheduleTask],
    *,
    width: int,
    workers: int | None,
    metadata: dict[str, Any] | None = None,
) -> ScheduledBatch:
    task_list = list(tasks)
    return ScheduledBatch(
        tasks=task_list,
        estimated_runtime=simulate_makespan(task_list, width=width, workers=workers),
        metadata=dict(metadata or {}),
    )


def _best_fit_by_simulated_height(
    units: Sequence[Sequence[ScheduleTask]],
    *,
    width: int,
    height: float,
    workers: int | None,
    metadata: dict[str, Any] | None = None,
) -> list[ScheduledBatch]:
    """Best-fit decreasing placement using simulated runtime as bin load."""

    unit_list = [list(unit) for unit in units if unit]

    ordered_units = sorted(
        unit_list,
        key=lambda unit: (
            simulate_makespan(unit, width=width, workers=workers),
            sum(task.scheduling_priority() for task in unit),
            sum(task.work() for task in unit),
        ),
        reverse=True,
    )

    batches: list[ScheduledBatch] = []

    for unit in ordered_units:
        best_index: int | None = None
        best_estimate: float | None = None
        best_slack: float | None = None

        for index, batch in enumerate(batches):
            candidate_tasks = batch.tasks + unit
            estimate = simulate_makespan(candidate_tasks, width=width, workers=workers)

            if estimate > height:
                continue

            slack = height - estimate

            if best_slack is None or slack < best_slack:
                best_index = index
                best_estimate = estimate
                best_slack = slack

        if best_index is None:
            batches.append(_make_batch(unit, width=width, workers=workers, metadata=metadata))
        else:
            assert best_estimate is not None
            batches[best_index].tasks.extend(unit)
            batches[best_index].estimated_runtime = best_estimate

    return [batch for batch in batches if batch]


def _partition_units_by_count(
    units: Sequence[Sequence[ScheduleTask]],
    *,
    count: int,
    width: int,
    workers: int | None,
    metadata: dict[str, Any] | None = None,
) -> list[ScheduledBatch]:
    """Greedy least-makespan partitioning of indivisible task units."""

    if count <= 0:
        raise ValueError(f"{count=} must be > 0")

    unit_list = [list(unit) for unit in units if unit]

    if not unit_list:
        return []

    ordered_units = sorted(
        unit_list,
        key=lambda unit: (
            simulate_makespan(unit, width=width, workers=workers),
            sum(task.scheduling_priority() for task in unit),
            sum(task.work() for task in unit),
        ),
        reverse=True,
    )

    # Explicit max behavior: if there is enough count for one batch per
    # indivisible unit, do not coalesce units merely because the simulated
    # makespan would be unchanged.
    if count >= len(ordered_units):
        return [
            _make_batch(unit, width=width, workers=workers, metadata=metadata)
            for unit in ordered_units
        ]

    nbatches = min(count, len(ordered_units))

    batches = [
        ScheduledBatch(tasks=[], estimated_runtime=0.0, metadata=dict(metadata or {}))
        for _ in range(nbatches)
    ]

    for unit in ordered_units:
        best_index: int | None = None
        best_estimate: float | None = None
        best_size: int | None = None

        for index, batch in enumerate(batches):
            candidate_tasks = batch.tasks + unit
            estimate = simulate_makespan(candidate_tasks, width=width, workers=workers)

            candidate_size = len(batch.tasks)

            if (
                best_estimate is None
                or estimate < best_estimate
                or (estimate == best_estimate and candidate_size < (best_size or 0))
            ):
                best_index = index
                best_estimate = estimate
                best_size = candidate_size

        assert best_index is not None
        assert best_estimate is not None

        batches[best_index].tasks.extend(unit)
        batches[best_index].estimated_runtime = best_estimate

    return [batch for batch in batches if batch]


def _topological_levels(tasks: Sequence[ScheduleTask]) -> list[list[ScheduleTask]]:
    """Return topological ready levels for the given task set."""

    task_by_id = {task.id: task for task in tasks}
    task_ids = set(task_by_id)

    graph: dict[str, list[str]] = {
        task.id: [dep for dep in task.dependencies if dep in task_ids] for task in tasks
    }

    ts = TopologicalSorter(graph)
    ts.prepare()

    levels: list[list[ScheduleTask]] = []

    while ts.is_active():
        ready_ids = list(ts.get_ready())
        ready = [task_by_id[task_id] for task_id in ready_ids]
        ready.sort(key=_priority_key, reverse=True)
        levels.append(ready)
        ts.done(*ready_ids)

    return levels


def _dependency_components(tasks: Sequence[ScheduleTask]) -> list[list[ScheduleTask]]:
    """Return dependency-connected components, ignoring edge direction."""

    task_by_id = {task.id: task for task in tasks}
    task_ids = set(task_by_id)

    neighbors: dict[str, set[str]] = {task.id: set() for task in tasks}

    for task in tasks:
        for dep in task.dependencies:
            if dep not in task_ids:
                continue

            neighbors[task.id].add(dep)
            neighbors[dep].add(task.id)

    seen: set[str] = set()
    components: list[list[ScheduleTask]] = []

    for task in tasks:
        if task.id in seen:
            continue

        component_ids: list[str] = []
        stack = [task.id]
        seen.add(task.id)

        while stack:
            current = stack.pop()
            component_ids.append(current)

            for neighbor in neighbors[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)

        component = [task_by_id[task_id] for task_id in component_ids]
        component.sort(key=_priority_key, reverse=True)
        components.append(component)

    components.sort(
        key=lambda component: (
            simulate_makespan(component, width=max(task.width for task in tasks), workers=None),
            sum(task.scheduling_priority() for task in component),
        ),
        reverse=True,
    )

    return components


def _priority_key(task: ScheduleTask) -> tuple[float, float, int, str]:
    """Return the scheduler priority key.

    Higher values sort earlier.
    """
    return (task.scheduling_priority(), float(task.duration), int(task.width), str(task.id))


def _effective_workers(workers: int | None, ntasks: int) -> int:
    if ntasks <= 0:
        return 0

    if workers is None or workers <= 0:
        return ntasks

    return min(workers, ntasks)


def _validate_tasks(tasks: Iterable[ScheduleTask], *, width: int) -> list[ScheduleTask]:
    if width <= 0:
        raise ValueError(f"{width=} must be > 0")

    task_list = list(tasks)

    counts = Counter(task.id for task in task_list)
    duplicates = sorted(task_id for task_id, count in counts.items() if count > 1)

    if duplicates:
        raise ValueError(f"ScheduleTask ids must be unique; duplicates: {duplicates}")

    too_wide = [task for task in task_list if task.width > width]

    if too_wide:
        details = ", ".join(f"{task.id}:width={task.width}" for task in too_wide)
        raise ValueError(f"Tasks exceed available {width=}: {details}")

    return task_list
