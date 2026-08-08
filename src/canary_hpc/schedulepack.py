# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Fast schedule-aware packing helpers for Canary HPC batching.

The packers in this module produce "good enough" batches quickly for large test
suites.  They use cheap incremental lower-bound makespan estimates for placement
decisions instead of repeatedly calling ``simulate_makespan`` on growing
candidate task lists.

``simulate_makespan`` remains available as the exact standalone simulator for
tests, diagnostics, and external callers.
"""

import dataclasses
import heapq
import math
from collections.abc import Iterable
from collections.abc import Sequence
from graphlib import CycleError
from graphlib import TopologicalSorter
from typing import Callable


@dataclasses.dataclass(frozen=True)
class ScheduleTask:
    """A task to be placed in a scheduler batch."""

    id: str
    width: int = 1
    duration: float = 1.0
    dependencies: tuple[str, ...] = dataclasses.field(default_factory=tuple)
    priority: float | None = None
    payload: object | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must be non-empty")

        if self.width <= 0:
            raise ValueError("width must be > 0")

        if self.duration < 0:
            raise ValueError("duration must be >= 0")

        object.__setattr__(self, "dependencies", tuple(self.dependencies))

    def default_priority(self) -> float:
        return math.sqrt(float(self.width) ** 2 + float(self.duration) ** 2)

    def scheduling_priority(self) -> float:
        return self.default_priority() if self.priority is None else float(self.priority)

    def work(self) -> float:
        return float(self.width) * float(self.duration)


@dataclasses.dataclass
class ScheduledBatch:
    """A packed batch of schedule tasks."""

    tasks: list[ScheduleTask]
    estimated_runtime: float = 0.0
    metadata: dict[str, object] = dataclasses.field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.tasks)

    def __bool__(self) -> bool:
        return bool(self.tasks)

    @property
    def ids(self) -> list[str]:
        return [task.id for task in self.tasks]

    @property
    def total_width(self) -> int:
        return sum(task.width for task in self.tasks)

    @property
    def total_duration(self) -> float:
        return sum(float(task.duration) for task in self.tasks)

    @property
    def total_work(self) -> float:
        return sum(task.work() for task in self.tasks)

    def recompute_runtime(self, estimator: Callable[[Sequence[ScheduleTask]], float]) -> None:
        self.estimated_runtime = float(estimator(self.tasks))


@dataclasses.dataclass(slots=True)
class CheapMakespanStats:
    """Incremental lower-bound makespan state.

    The estimate is:

        max(
            max task duration,
            total work / scheduler width,
            total duration / workers, if workers is set,
            critical path lower bound,
        )

    This is intentionally a cheap estimate, not an exact simulation.
    """

    total_work: float = 0.0
    total_duration: float = 0.0
    max_duration: float = 0.0
    max_width: int = 0
    critical_path: float = 0.0
    count: int = 0

    def add(self, task: ScheduleTask) -> None:
        self.total_work += task.work()
        self.total_duration += float(task.duration)
        self.max_duration = max(self.max_duration, float(task.duration))
        self.max_width = max(self.max_width, int(task.width))
        self.count += 1

    def add_many(self, tasks: Iterable[ScheduleTask], *, critical_path: float = 0.0) -> None:
        for task in tasks:
            self.add(task)

        self.critical_path = max(self.critical_path, float(critical_path))

    def estimate(self, *, width: int, workers: int | None = None) -> float:
        if width <= 0:
            raise ValueError(f"width={width!r} must be > 0")

        if workers is not None and workers <= 0:
            raise ValueError(f"workers={workers!r} must be > 0")

        if self.count == 0:
            return 0.0

        if self.max_width > width:
            raise ValueError(
                f"Tasks exceed available width: max task width {self.max_width}, "
                f"available width is {width}"
            )

        estimate = max(self.max_duration, self.total_work / float(width), self.critical_path)

        if workers is not None:
            estimate = max(estimate, self.total_duration / float(workers))

        return estimate

    def estimate_with_task(
        self, task: ScheduleTask, *, width: int, workers: int | None = None
    ) -> float:
        return self.estimate_with_tasks([task], width=width, workers=workers)

    def estimate_with_tasks(
        self,
        tasks: Sequence[ScheduleTask],
        *,
        width: int,
        workers: int | None = None,
        critical_path: float = 0.0,
    ) -> float:
        if width <= 0:
            raise ValueError(f"width={width!r} must be > 0")

        if workers is not None and workers <= 0:
            raise ValueError(f"workers={workers!r} must be > 0")

        total_work = self.total_work
        total_duration = self.total_duration
        max_duration = self.max_duration
        max_width = self.max_width

        for task in tasks:
            total_work += task.work()
            total_duration += float(task.duration)
            max_duration = max(max_duration, float(task.duration))
            max_width = max(max_width, int(task.width))

        if max_width > width:
            raise ValueError(
                f"Tasks exceed available width: max task width {max_width}, "
                f"available width is {width}"
            )

        estimate = max(
            max_duration, total_work / float(width), self.critical_path, float(critical_path)
        )

        if workers is not None:
            estimate = max(estimate, total_duration / float(workers))

        return estimate


def cheap_makespan(
    tasks: Sequence[ScheduleTask],
    *,
    width: int,
    workers: int | None = None,
    critical_path: bool = True,
    validate: bool = True,
) -> float:
    """Return a cheap lower-bound estimate of makespan.

    Dependencies outside ``tasks`` are ignored.

    This function is intended for packing decisions.  It is not an exact
    scheduler simulation.
    """
    if width <= 0:
        raise ValueError(f"width={width!r} must be > 0")

    if workers is not None and workers <= 0:
        raise ValueError(f"workers={workers!r} must be > 0")

    if not tasks:
        return 0.0

    if validate:
        _validate_tasks(tasks, width=width)

    stats = CheapMakespanStats()

    for task in tasks:
        stats.add(task)

    if critical_path:
        stats.critical_path = _critical_path_lower_bound(tasks)

    return stats.estimate(width=width, workers=workers)


def simulate_makespan(
    tasks: Sequence[ScheduleTask], *, width: int, workers: int | None = None
) -> float:
    """Simulate a simple resource-aware scheduler and return exact makespan.

    This public function preserves exact simulator behavior for external
    callers.  The packers avoid calling it in placement hot loops.
    """
    if width <= 0:
        raise ValueError(f"width={width!r} must be > 0")

    if workers is not None and workers <= 0:
        raise ValueError(f"workers={workers!r} must be > 0")

    if not tasks:
        return 0.0

    _validate_tasks(tasks, width=width)

    task_by_id = {task.id: task for task in tasks}
    task_ids = set(task_by_id)

    successors: dict[str, list[str]] = {task.id: [] for task in tasks}
    indegree: dict[str, int] = {task.id: 0 for task in tasks}

    for task in tasks:
        for dep_id in task.dependencies:
            if dep_id not in task_ids:
                continue

            successors[dep_id].append(task.id)
            indegree[task.id] += 1

    ready: list[str] = [task_id for task_id, degree in indegree.items() if degree == 0]

    now = 0.0
    available_width = width
    running_workers = 0
    max_workers = workers if workers is not None else len(tasks)

    # Heap entries are: (finish_time, sequence_number, task_id)
    running: list[tuple[float, int, str]] = []
    sequence = 0
    completed = 0

    def ready_sort_key(task_id: str) -> tuple[float, float, int, str]:
        task = task_by_id[task_id]
        return (task.scheduling_priority(), float(task.duration), int(task.width), str(task.id))

    while completed < len(tasks):
        started = True

        while started and ready:
            started = False
            ready.sort(key=ready_sort_key, reverse=True)

            for index, task_id in enumerate(list(ready)):
                task = task_by_id[task_id]

                if task.width > available_width:
                    continue

                if running_workers >= max_workers:
                    continue

                ready.pop(index)

                available_width -= task.width
                running_workers += 1

                finish_time = now + float(task.duration)
                heapq.heappush(running, (finish_time, sequence, task_id))
                sequence += 1
                started = True
                break

        if not running:
            if ready:
                raise RuntimeError(
                    "Scheduler made no progress despite ready tasks; "
                    "check width/workers constraints"
                )

            raise ValueError("Dependency cycle detected")

        next_finish = running[0][0]
        now = max(now, next_finish)

        while running and running[0][0] <= now:
            _, _, task_id = heapq.heappop(running)
            task = task_by_id[task_id]

            available_width += task.width
            running_workers -= 1
            completed += 1

            for child_id in successors[task_id]:
                indegree[child_id] -= 1

                if indegree[child_id] == 0:
                    ready.append(child_id)

    return now


def pack_to_height_simulated(
    tasks: Sequence[ScheduleTask], *, width: int, height: float, workers: int | None = None
) -> list[ScheduledBatch]:
    """Pack flat batches using a cheap target-height estimate.

    Despite the historical name, this function does not repeatedly simulate
    candidate batches.  It computes an estimated number of batches per
    topological level and then uses fast heap-based count packing.
    """
    if width <= 0:
        raise ValueError(f"width={width!r} must be > 0")

    if height <= 0:
        raise ValueError(f"height={height!r} must be > 0")

    if workers is not None and workers <= 0:
        raise ValueError(f"workers={workers!r} must be > 0")

    if not tasks:
        return []

    _validate_tasks(tasks, width=width)

    result: list[ScheduledBatch] = []

    for level in _topological_levels(tasks):
        count = _estimate_count_for_height(level, width=width, height=height, workers=workers)

        result.extend(
            _pack_independent_by_count_cheap(
                level,
                width=width,
                count=count,
                workers=workers,
                algorithm="pack_to_height_simulated",
                extra_metadata={"layout": "flat", "target_height": float(height)},
            )
        )

    return result


def pack_by_count_simulated(
    tasks: Sequence[ScheduleTask], *, width: int, count: int, workers: int | None = None
) -> list[ScheduledBatch]:
    """Pack flat batches by count using cheap heap-based load balancing.

    Topological levels are kept separate, so dependencies inside a returned
    flat batch are avoided.
    """
    if width <= 0:
        raise ValueError(f"width={width!r} must be > 0")

    if count <= 0:
        raise ValueError(f"count={count!r} must be > 0")

    if workers is not None and workers <= 0:
        raise ValueError(f"workers={workers!r} must be > 0")

    if not tasks:
        return []

    _validate_tasks(tasks, width=width)

    levels = _topological_levels(tasks)

    if count < len(levels):
        raise ValueError(
            f"count={count} is insufficient for flat layout with {len(levels)} topological levels"
        )

    count = min(count, len(tasks))
    level_counts = _allocate_counts(count, levels, width=width, workers=workers)

    result: list[ScheduledBatch] = []

    for level, level_count in zip(levels, level_counts):
        result.extend(
            _pack_independent_by_count_cheap(
                level,
                width=width,
                count=level_count,
                workers=workers,
                algorithm="pack_by_count_simulated",
                extra_metadata={"layout": "flat"},
            )
        )

    return result


def pack_by_count_atomic_simulated(
    tasks: Sequence[ScheduleTask], *, width: int, count: int, workers: int | None = None
) -> list[ScheduledBatch]:
    """Pack atomic batches by dependency-connected components.

    Dependency-connected components are kept intact. Components are assigned to
    batches with heap-based lower-bound load balancing.
    """
    if width <= 0:
        raise ValueError(f"width={width!r} must be > 0")

    if count <= 0:
        raise ValueError(f"count={count!r} must be > 0")

    if workers is not None and workers <= 0:
        raise ValueError(f"workers={workers!r} must be > 0")

    if not tasks:
        return []

    _validate_tasks(tasks, width=width)
    _assert_acyclic(tasks)

    components = _dependency_components(tasks, width=width, workers=workers)

    if not components:
        return []

    count = min(count, len(components))

    component_infos: list[_ComponentInfo] = []

    for component in components:
        critical_path = _critical_path_lower_bound(component)

        component_infos.append(
            _ComponentInfo(
                tasks=component,
                estimated_runtime=cheap_makespan(
                    component, width=width, workers=workers, critical_path=True, validate=False
                ),
                total_work=sum(task.work() for task in component),
                total_duration=sum(float(task.duration) for task in component),
                max_duration=max((float(task.duration) for task in component), default=0.0),
                critical_path=critical_path,
            )
        )

    component_infos.sort(
        key=lambda c: (
            c.estimated_runtime,
            c.total_work,
            c.total_duration,
            len(c.tasks),
            min((task.id for task in c.tasks), default=""),
        ),
        reverse=True,
    )

    accums = [_BatchAccum() for _ in range(count)]

    heap: list[tuple[float, int, float, float, int]] = [
        accums[i].heap_key(width=width, workers=workers, index=i) for i in range(count)
    ]
    heapq.heapify(heap)

    for component in component_infos:
        *_, batch_index = heapq.heappop(heap)

        accum = accums[batch_index]
        accum.tasks.extend(component.tasks)
        accum.stats.add_many(component.tasks, critical_path=component.critical_path)

        heapq.heappush(heap, accum.heap_key(width=width, workers=workers, index=batch_index))

    result: list[ScheduledBatch] = []

    for accum in accums:
        if not accum.tasks:
            continue

        estimated_runtime = cheap_makespan(
            accum.tasks, width=width, workers=workers, critical_path=True, validate=False
        )

        result.append(
            ScheduledBatch(
                tasks=accum.tasks,
                estimated_runtime=estimated_runtime,
                metadata={
                    "algorithm": "pack_by_count_atomic_simulated",
                    "layout": "atomic",
                    "width": width,
                    "workers": workers,
                },
            )
        )

    return result


@dataclasses.dataclass
class _BatchAccum:
    tasks: list[ScheduleTask] = dataclasses.field(default_factory=list)
    stats: CheapMakespanStats = dataclasses.field(default_factory=CheapMakespanStats)

    def heap_key(
        self, *, width: int, workers: int | None, index: int
    ) -> tuple[float, int, float, float, int]:
        """Return a stable heap key for choosing the least-loaded batch.

        The first element is the cheap makespan estimate.  The remaining fields
        break ties in favor of batches with fewer tasks and less accumulated
        work.  This matters because the lower-bound estimate can remain flat
        when adding tasks that fit in parallel.
        """
        return (
            self.stats.estimate(width=width, workers=workers),
            self.stats.count,
            self.stats.total_work,
            self.stats.total_duration,
            index,
        )


@dataclasses.dataclass(frozen=True)
class _ComponentInfo:
    tasks: list[ScheduleTask]
    estimated_runtime: float
    total_work: float
    total_duration: float
    max_duration: float
    critical_path: float


def _pack_independent_by_count_cheap(
    tasks: Sequence[ScheduleTask],
    *,
    width: int,
    count: int,
    workers: int | None,
    algorithm: str,
    extra_metadata: dict[str, object] | None = None,
) -> list[ScheduledBatch]:
    """Pack independent tasks into ``count`` batches using heap load balancing."""

    if not tasks:
        return []

    if count <= 0:
        raise ValueError(f"count={count!r} must be > 0")

    count = min(count, len(tasks))

    ordered = sorted(
        tasks,
        key=lambda task: (
            task.scheduling_priority(),
            task.work(),
            float(task.duration),
            int(task.width),
            str(task.id),
        ),
        reverse=True,
    )

    accums = [_BatchAccum() for _ in range(count)]

    heap: list[tuple[float, int, float, float, int]] = [
        accums[i].heap_key(width=width, workers=workers, index=i) for i in range(count)
    ]
    heapq.heapify(heap)

    for task in ordered:
        *_, batch_index = heapq.heappop(heap)

        accum = accums[batch_index]
        accum.tasks.append(task)
        accum.stats.add(task)

        heapq.heappush(heap, accum.heap_key(width=width, workers=workers, index=batch_index))

    result: list[ScheduledBatch] = []

    for accum in accums:
        if not accum.tasks:
            continue

        estimated_runtime = accum.stats.estimate(width=width, workers=workers)

        metadata: dict[str, object] = {"algorithm": algorithm, "width": width, "workers": workers}

        if extra_metadata:
            metadata.update(extra_metadata)

        result.append(
            ScheduledBatch(
                tasks=accum.tasks, estimated_runtime=estimated_runtime, metadata=metadata
            )
        )

    return result


def _estimate_count_for_height(
    tasks: Sequence[ScheduleTask], *, width: int, height: float, workers: int | None
) -> int:
    if not tasks:
        return 0

    total_work = sum(task.work() for task in tasks)
    total_duration = sum(float(task.duration) for task in tasks)
    max_task_height = max((float(task.duration) for task in tasks), default=0.0)

    count = max(1, math.ceil(total_work / (float(width) * float(height))))

    if workers is not None:
        count = max(count, math.ceil(total_duration / (float(workers) * float(height))))

    # A single over-target task is allowed and must live in one batch.
    if max_task_height > height:
        over_target = sum(1 for task in tasks if float(task.duration) > height)
        count = max(count, over_target)

    return min(max(count, 1), len(tasks))


def _allocate_counts(
    count: int, levels: Sequence[Sequence[ScheduleTask]], *, width: int, workers: int | None
) -> list[int]:
    """Allocate a global count across topological levels.

    Every non-empty level gets at least one batch. Remaining batches are
    distributed by cheap estimated level load.
    """
    nonempty = [list(level) for level in levels if level]

    if not nonempty:
        return []

    if count < len(nonempty):
        raise ValueError(f"count={count} is insufficient for {len(nonempty)} levels")

    capacities = [len(level) for level in nonempty]
    count = min(count, sum(capacities))

    allocations = [1 for _ in nonempty]
    room = [capacity - 1 for capacity in capacities]
    remaining = count - len(nonempty)

    if remaining <= 0:
        return allocations

    weights = [
        cheap_makespan(level, width=width, workers=workers, critical_path=False, validate=False)
        for level in nonempty
    ]

    total_weight = sum(weights)

    if total_weight <= 0.0:
        weights = [float(len(level)) for level in nonempty]
        total_weight = sum(weights)

    if total_weight <= 0.0:
        return allocations

    quotas = [remaining * weight / total_weight for weight in weights]
    additions = [min(room[i], int(math.floor(quotas[i]))) for i in range(len(nonempty))]

    for i, addition in enumerate(additions):
        allocations[i] += addition
        room[i] -= addition
        remaining -= addition

    order = sorted(
        range(len(nonempty)),
        key=lambda i: (quotas[i] - math.floor(quotas[i]), weights[i]),
        reverse=True,
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

    return allocations


def _topological_levels(tasks: Sequence[ScheduleTask]) -> list[list[ScheduleTask]]:
    """Return topological ready levels for tasks.

    Dependencies outside ``tasks`` are ignored.
    """
    task_by_id = {task.id: task for task in tasks}
    task_ids = set(task_by_id)

    graph: dict[str, list[str]] = {}

    for task in tasks:
        graph[task.id] = [dep_id for dep_id in task.dependencies if dep_id in task_ids]

    sorter = TopologicalSorter(graph)

    try:
        sorter.prepare()
    except CycleError as e:
        raise ValueError("Dependency cycle detected") from e

    levels: list[list[ScheduleTask]] = []

    while sorter.is_active():
        ready_ids = list(sorter.get_ready())
        ready_tasks = [task_by_id[task_id] for task_id in ready_ids]

        ready_tasks.sort(
            key=lambda task: (
                task.scheduling_priority(),
                float(task.duration),
                int(task.width),
                str(task.id),
            ),
            reverse=True,
        )

        levels.append(ready_tasks)
        sorter.done(*ready_ids)

    return levels


def _dependency_components(
    tasks: Sequence[ScheduleTask], *, width: int, workers: int | None
) -> list[list[ScheduleTask]]:
    """Return undirected dependency-connected components.

    Dependencies outside ``tasks`` are ignored.

    The component ordering uses the caller's actual ``width`` and ``workers``.
    This fixes the previous bug where ordering was computed using
    ``max(task.width)`` and ``workers=None`` regardless of caller settings.
    """
    task_by_id = {task.id: task for task in tasks}
    task_ids = set(task_by_id)

    adjacency: dict[str, set[str]] = {task.id: set() for task in tasks}

    for task in tasks:
        for dep_id in task.dependencies:
            if dep_id not in task_ids:
                continue

            adjacency[task.id].add(dep_id)
            adjacency[dep_id].add(task.id)

    visited: set[str] = set()
    components: list[list[ScheduleTask]] = []

    for task in tasks:
        if task.id in visited:
            continue

        stack = [task.id]
        visited.add(task.id)
        component_ids: list[str] = []

        while stack:
            task_id = stack.pop()
            component_ids.append(task_id)

            for neighbor in sorted(adjacency[task_id]):
                if neighbor in visited:
                    continue

                visited.add(neighbor)
                stack.append(neighbor)

        component = [task_by_id[task_id] for task_id in component_ids]
        component.sort(
            key=lambda t: (t.scheduling_priority(), float(t.duration), int(t.width), str(t.id)),
            reverse=True,
        )
        components.append(component)

    components.sort(
        key=lambda component: (
            cheap_makespan(
                component, width=width, workers=workers, critical_path=True, validate=False
            ),
            sum(task.scheduling_priority() for task in component),
            len(component),
            min((task.id for task in component), default=""),
        ),
        reverse=True,
    )

    return components


def _critical_path_lower_bound(tasks: Sequence[ScheduleTask]) -> float:
    """Return internal dependency critical-path duration.

    Dependencies outside ``tasks`` are ignored.
    """
    if not tasks:
        return 0.0

    task_by_id = {task.id: task for task in tasks}
    task_ids = set(task_by_id)

    if len(task_by_id) != len(tasks):
        raise ValueError("task ids must be unique")

    successors: dict[str, list[str]] = {task.id: [] for task in tasks}
    indegree: dict[str, int] = {task.id: 0 for task in tasks}
    earliest_finish: dict[str, float] = {task.id: float(task.duration) for task in tasks}

    for task in tasks:
        for dep_id in task.dependencies:
            if dep_id not in task_ids:
                continue

            successors[dep_id].append(task.id)
            indegree[task.id] += 1

    ready = [task_id for task_id, degree in indegree.items() if degree == 0]
    visited = 0

    while ready:
        task_id = ready.pop()
        visited += 1
        finish_time = earliest_finish[task_id]

        for child_id in successors[task_id]:
            child = task_by_id[child_id]
            candidate_finish = finish_time + float(child.duration)

            if candidate_finish > earliest_finish[child_id]:
                earliest_finish[child_id] = candidate_finish

            indegree[child_id] -= 1

            if indegree[child_id] == 0:
                ready.append(child_id)

    if visited != len(tasks):
        raise ValueError("Dependency cycle detected")

    return max(earliest_finish.values(), default=0.0)


def _assert_acyclic(tasks: Sequence[ScheduleTask]) -> None:
    _critical_path_lower_bound(tasks)


def _validate_tasks(tasks: Sequence[ScheduleTask], *, width: int) -> None:
    if width <= 0:
        raise ValueError(f"width={width!r} must be > 0")

    ids = [task.id for task in tasks]

    if len(set(ids)) != len(ids):
        raise ValueError("task ids must be unique")

    too_wide = [task for task in tasks if task.width > width]

    if too_wide:
        task = max(too_wide, key=lambda t: t.width)
        raise ValueError(
            f"Tasks exceed available width: task {task.id!r} has width {task.width}, "
            f"available width is {width}"
        )
