# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from canary_hpc.schedulepack import ScheduledBatch
from canary_hpc.schedulepack import ScheduleTask
from canary_hpc.schedulepack import pack_by_count_atomic_simulated
from canary_hpc.schedulepack import pack_by_count_simulated
from canary_hpc.schedulepack import pack_to_height_simulated
from canary_hpc.schedulepack import simulate_makespan


def task(
    id: str,
    *,
    width: int = 1,
    duration: float = 1.0,
    dependencies: tuple[str, ...] = (),
    priority: float | None = None,
) -> ScheduleTask:
    return ScheduleTask(
        id=id, width=width, duration=duration, dependencies=dependencies, priority=priority
    )


def ids(batch: ScheduledBatch) -> set[str]:
    return {t.id for t in batch.tasks}


def find_batch_containing(batches: list[ScheduledBatch], task_id: str) -> ScheduledBatch:
    for batch in batches:
        if task_id in ids(batch):
            return batch
    raise AssertionError(f"No batch contains task {task_id!r}")


def test_schedule_task_normalizes_dependencies() -> None:
    t = ScheduleTask(
        id="a",
        width=2,
        duration=3.0,
        dependencies=["x", "y"],  # type: ignore[arg-type]
    )

    assert t.dependencies == ("x", "y")


def test_schedule_task_rejects_empty_id() -> None:
    with pytest.raises(ValueError, match="id must be non-empty"):
        ScheduleTask(id="", width=1, duration=1.0)


def test_schedule_task_rejects_nonpositive_width() -> None:
    with pytest.raises(ValueError, match="width must be > 0"):
        ScheduleTask(id="a", width=0, duration=1.0)


def test_schedule_task_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="duration must be >= 0"):
        ScheduleTask(id="a", width=1, duration=-1.0)


def test_schedule_task_default_priority_uses_width_and_duration() -> None:
    t = task("a", width=3, duration=4.0)

    assert t.default_priority() == pytest.approx(5.0)
    assert t.scheduling_priority() == pytest.approx(5.0)


def test_schedule_task_explicit_priority_overrides_default() -> None:
    t = task("a", width=3, duration=4.0, priority=99.0)

    assert t.default_priority() == pytest.approx(5.0)
    assert t.scheduling_priority() == pytest.approx(99.0)


def test_schedule_task_work() -> None:
    t = task("a", width=3, duration=4.0)

    assert t.work() == pytest.approx(12.0)


def test_scheduled_batch_properties() -> None:
    batch = ScheduledBatch(
        tasks=[task("a", width=2, duration=5.0), task("b", width=3, duration=7.0)],
        estimated_runtime=9.0,
    )

    assert len(batch) == 2
    assert bool(batch)
    assert batch.ids == ["a", "b"]
    assert batch.total_width == 5
    assert batch.total_duration == pytest.approx(12.0)
    assert batch.total_work == pytest.approx(31.0)


def test_scheduled_batch_recompute_runtime() -> None:
    batch = ScheduledBatch(
        tasks=[task("a", width=1, duration=2.0), task("b", width=1, duration=3.0)]
    )

    batch.recompute_runtime(lambda tasks: sum(t.duration for t in tasks))

    assert batch.estimated_runtime == pytest.approx(5.0)


def test_simulate_makespan_empty_task_list() -> None:
    assert simulate_makespan([], width=4) == pytest.approx(0.0)


def test_simulate_makespan_parallel_when_width_allows() -> None:
    tasks = [task("a", width=2, duration=10.0), task("b", width=2, duration=5.0)]

    assert simulate_makespan(tasks, width=4) == pytest.approx(10.0)


def test_simulate_makespan_serial_when_width_does_not_allow_parallelism() -> None:
    tasks = [task("a", width=2, duration=10.0), task("b", width=2, duration=5.0)]

    assert simulate_makespan(tasks, width=2) == pytest.approx(15.0)


def test_simulate_makespan_serial_when_worker_limit_is_one() -> None:
    tasks = [task("a", width=2, duration=10.0), task("b", width=2, duration=5.0)]

    assert simulate_makespan(tasks, width=4, workers=1) == pytest.approx(15.0)


def test_simulate_makespan_respects_dependencies() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=5.0, dependencies=("a",)),
    ]

    assert simulate_makespan(tasks, width=4) == pytest.approx(15.0)


def test_simulate_makespan_ignores_dependencies_outside_task_set() -> None:
    tasks = [task("a", width=1, duration=10.0, dependencies=("external",))]

    assert simulate_makespan(tasks, width=4) == pytest.approx(10.0)


def test_simulate_makespan_uses_priority_order() -> None:
    tasks = [
        task("short_low_priority", width=2, duration=1.0, priority=1.0),
        task("long_high_priority", width=2, duration=10.0, priority=100.0),
    ]

    # With width=2, only one task runs at a time.  The high priority task runs first.
    # Makespan is still the sum, but this test ensures the priority input is accepted.
    assert simulate_makespan(tasks, width=2) == pytest.approx(11.0)


def test_simulate_makespan_priority_affects_resource_contention() -> None:
    tasks = [
        task("wide", width=3, duration=10.0, priority=10.0),
        task("narrow_a", width=2, duration=100.0, priority=100.0),
        task("narrow_b", width=2, duration=100.0, priority=90.0),
    ]

    # width=4:
    # - narrow_a and narrow_b both start at t=0
    # - wide cannot fit until they finish
    # - wide then runs from t=100 to t=110
    assert simulate_makespan(tasks, width=4) == pytest.approx(110.0)


def test_simulate_makespan_rejects_duplicate_ids() -> None:
    tasks = [task("a", width=1, duration=1.0), task("a", width=1, duration=1.0)]

    with pytest.raises(ValueError, match="ids must be unique"):
        simulate_makespan(tasks, width=2)


def test_simulate_makespan_rejects_nonpositive_width() -> None:
    with pytest.raises(ValueError, match="width=.*must be > 0"):
        simulate_makespan([task("a")], width=0)


def test_simulate_makespan_rejects_task_wider_than_width() -> None:
    tasks = [task("a", width=5, duration=1.0)]

    with pytest.raises(ValueError, match="Tasks exceed available"):
        simulate_makespan(tasks, width=4)


def test_simulate_makespan_detects_dependency_cycle() -> None:
    tasks = [task("a", dependencies=("b",)), task("b", dependencies=("a",))]

    with pytest.raises(ValueError, match="Dependency cycle"):
        simulate_makespan(tasks, width=2)


def test_pack_to_height_simulated_packs_independent_tasks_by_target_height() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=10.0),
        task("c", width=1, duration=10.0),
        task("d", width=1, duration=10.0),
    ]

    batches = pack_to_height_simulated(tasks, width=2, height=10.0)

    assert len(batches) == 2
    assert sorted(len(batch) for batch in batches) == [2, 2]
    assert all(batch.estimated_runtime == pytest.approx(10.0) for batch in batches)

    packed_ids = set().union(*(ids(batch) for batch in batches))
    assert packed_ids == {"a", "b", "c", "d"}


def test_pack_to_height_simulated_allows_over_target_single_task() -> None:
    tasks = [task("a", width=1, duration=20.0)]

    batches = pack_to_height_simulated(tasks, width=2, height=10.0)

    assert len(batches) == 1
    assert ids(batches[0]) == {"a"}
    assert batches[0].estimated_runtime == pytest.approx(20.0)


def test_pack_to_height_simulated_uses_flat_topological_levels() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=5.0, dependencies=("a",)),
        task("c", width=1, duration=10.0),
        task("d", width=1, duration=5.0, dependencies=("c",)),
    ]

    batches = pack_to_height_simulated(tasks, width=2, height=10.0)

    assert len(batches) == 2

    batch_sets = [ids(batch) for batch in batches]

    assert {"a", "c"} in batch_sets
    assert {"b", "d"} in batch_sets


def test_pack_to_height_simulated_rejects_invalid_height() -> None:
    with pytest.raises(ValueError, match="height=.*must be > 0"):
        pack_to_height_simulated([task("a")], width=1, height=0.0)


def test_pack_by_count_simulated_splits_independent_tasks() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=10.0),
        task("c", width=1, duration=10.0),
        task("d", width=1, duration=10.0),
    ]

    batches = pack_by_count_simulated(tasks, width=2, count=2)

    assert len(batches) == 2
    assert sorted(len(batch) for batch in batches) == [2, 2]
    assert all(batch.estimated_runtime == pytest.approx(10.0) for batch in batches)

    packed_ids = set().union(*(ids(batch) for batch in batches))
    assert packed_ids == {"a", "b", "c", "d"}


def test_pack_by_count_simulated_count_at_least_ntasks_gives_one_task_per_batch() -> None:
    tasks = [task("a", width=1, duration=10.0), task("b", width=1, duration=10.0)]

    batches = pack_by_count_simulated(tasks, width=2, count=10)

    assert len(batches) == 2
    assert {frozenset(ids(batch)) for batch in batches} == {frozenset({"a"}), frozenset({"b"})}
    assert all(batch.estimated_runtime == pytest.approx(10.0) for batch in batches)


def test_pack_by_count_simulated_requires_count_at_least_topological_levels() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=5.0, dependencies=("a",)),
    ]

    with pytest.raises(ValueError, match="insufficient for flat layout"):
        pack_by_count_simulated(tasks, width=2, count=1)


def test_pack_by_count_simulated_dependency_chain_with_sufficient_count() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=5.0, dependencies=("a",)),
    ]

    batches = pack_by_count_simulated(tasks, width=2, count=2)

    assert len(batches) == 2
    assert {frozenset(ids(batch)) for batch in batches} == {frozenset({"a"}), frozenset({"b"})}


def test_pack_by_count_simulated_rejects_nonpositive_count() -> None:
    with pytest.raises(ValueError, match="count=.*must be > 0"):
        pack_by_count_simulated([task("a")], width=1, count=0)


def test_pack_by_count_atomic_simulated_keeps_dependency_components_together() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=5.0, dependencies=("a",)),
        task("c", width=1, duration=8.0),
        task("d", width=1, duration=3.0, dependencies=("c",)),
        task("e", width=1, duration=7.0),
    ]

    batches = pack_by_count_atomic_simulated(tasks, width=2, count=2)

    assert len(batches) == 2

    batch_a = find_batch_containing(batches, "a")
    batch_b = find_batch_containing(batches, "b")
    batch_c = find_batch_containing(batches, "c")
    batch_d = find_batch_containing(batches, "d")

    assert batch_a is batch_b
    assert batch_c is batch_d

    packed_ids = set().union(*(ids(batch) for batch in batches))
    assert packed_ids == {"a", "b", "c", "d", "e"}


def test_pack_by_count_atomic_simulated_may_return_fewer_batches_than_count() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=5.0, dependencies=("a",)),
    ]

    batches = pack_by_count_atomic_simulated(tasks, width=2, count=10)

    assert len(batches) == 1
    assert ids(batches[0]) == {"a", "b"}
    assert batches[0].estimated_runtime == pytest.approx(15.0)


def test_pack_by_count_atomic_simulated_rejects_nonpositive_count() -> None:
    with pytest.raises(ValueError, match="count=.*must be > 0"):
        pack_by_count_atomic_simulated([task("a")], width=1, count=0)


def test_pack_by_count_atomic_simulated_independent_tasks_can_share_batch() -> None:
    tasks = [
        task("a", width=1, duration=10.0),
        task("b", width=1, duration=10.0),
        task("c", width=1, duration=10.0),
        task("d", width=1, duration=10.0),
    ]

    batches = pack_by_count_atomic_simulated(tasks, width=2, count=2)

    assert len(batches) == 2
    assert sorted(len(batch) for batch in batches) == [2, 2]
    assert all(batch.estimated_runtime == pytest.approx(10.0) for batch in batches)


def test_packers_attach_metadata() -> None:
    tasks = [task("a", width=1, duration=10.0), task("b", width=1, duration=10.0)]

    by_height = pack_to_height_simulated(tasks, width=2, height=10.0)
    by_count = pack_by_count_simulated(tasks, width=2, count=2)
    atomic = pack_by_count_atomic_simulated(tasks, width=2, count=2)

    assert by_height
    assert by_count
    assert atomic

    assert by_height[0].metadata["algorithm"] == "pack_to_height_simulated"
    assert by_count[0].metadata["algorithm"] == "pack_by_count_simulated"
    assert atomic[0].metadata["algorithm"] == "pack_by_count_atomic_simulated"

    assert by_height[0].metadata["width"] == 2
    assert by_count[0].metadata["width"] == 2
    assert atomic[0].metadata["width"] == 2


def make_large_flat_tasks(n: int) -> list[ScheduleTask]:
    """Create a large mostly-flat task set with two topological levels.

    The first group contains root tasks.  Some later tasks depend on one of
    those roots, while others have only external dependencies that are ignored
    by the packer.  This keeps the flat count requirement modest while still
    exercising dependency handling.
    """
    roots = min(128, max(1, n))
    tasks: list[ScheduleTask] = []

    for i in range(roots):
        tasks.append(
            task(
                f"root-{i}", width=1 + (i % 8), duration=5.0 + float(i % 31), priority=float(i % 97)
            )
        )

    for i in range(roots, n):
        dependencies = (f"root-{i % roots}",) if i % 7 == 0 else ("external",)

        tasks.append(
            task(
                f"task-{i}",
                width=1 + (i % 8),
                duration=1.0 + float((i * 17) % 113),
                dependencies=dependencies,
                priority=float((i * 19) % 101),
            )
        )

    return tasks


def make_large_atomic_tasks(n: int) -> list[ScheduleTask]:
    """Create many small dependency-connected components."""
    tasks: list[ScheduleTask] = []

    i = 0
    component = 0

    while i < n:
        a = f"component-{component}-a"
        b = f"component-{component}-b"
        c = f"component-{component}-c"

        tasks.append(
            task(
                a,
                width=1 + (component % 4),
                duration=2.0 + float(component % 17),
                priority=float(component % 53),
            )
        )
        i += 1

        if i < n:
            tasks.append(
                task(
                    b,
                    width=1 + ((component + 1) % 4),
                    duration=3.0 + float(component % 19),
                    dependencies=(a,),
                    priority=float((component * 3) % 53),
                )
            )
            i += 1

        if i < n:
            tasks.append(
                task(
                    c,
                    width=1 + ((component + 2) % 4),
                    duration=1.0 + float(component % 23),
                    dependencies=(b,),
                    priority=float((component * 7) % 53),
                )
            )
            i += 1

        component += 1

    return tasks


def assert_all_tasks_packed_once(batches: list[ScheduledBatch], tasks: list[ScheduleTask]) -> None:
    packed = [t.id for batch in batches for t in batch.tasks]
    expected = [t.id for t in tasks]

    assert len(packed) == len(expected)
    assert set(packed) == set(expected)
    assert len(set(packed)) == len(packed)


def assert_flat_batches_have_no_internal_dependencies(batches: list[ScheduledBatch]) -> None:
    for batch in batches:
        ids = {t.id for t in batch.tasks}

        for t in batch.tasks:
            assert not any(dep_id in ids for dep_id in t.dependencies)


def assert_batch_metadata(batches: list[ScheduledBatch], *, algorithm: str, width: int) -> None:
    assert batches

    for batch in batches:
        assert batch.metadata["algorithm"] == algorithm
        assert batch.metadata["width"] == width


def test_pack_by_count_simulated_does_not_call_exact_simulator(monkeypatch) -> None:
    tasks = make_large_flat_tasks(1000)

    def fail(*args, **kwargs):
        raise AssertionError("pack_by_count_simulated should not call simulate_makespan")

    monkeypatch.setitem(pack_by_count_simulated.__globals__, "simulate_makespan", fail)

    batches = pack_by_count_simulated(tasks, width=16, count=16, workers=8)

    assert_all_tasks_packed_once(batches, tasks)
    assert_flat_batches_have_no_internal_dependencies(batches)
    assert_batch_metadata(batches, algorithm="pack_by_count_simulated", width=16)


def test_pack_to_height_simulated_does_not_call_exact_simulator(monkeypatch) -> None:
    tasks = make_large_flat_tasks(1000)

    def fail(*args, **kwargs):
        raise AssertionError("pack_to_height_simulated should not call simulate_makespan")

    monkeypatch.setitem(pack_to_height_simulated.__globals__, "simulate_makespan", fail)

    batches = pack_to_height_simulated(tasks, width=16, height=300.0, workers=8)

    assert_all_tasks_packed_once(batches, tasks)
    assert_flat_batches_have_no_internal_dependencies(batches)
    assert_batch_metadata(batches, algorithm="pack_to_height_simulated", width=16)


def test_pack_by_count_atomic_simulated_does_not_call_exact_simulator(monkeypatch) -> None:
    tasks = make_large_atomic_tasks(1000)

    def fail(*args, **kwargs):
        raise AssertionError("pack_by_count_atomic_simulated should not call simulate_makespan")

    monkeypatch.setitem(pack_by_count_atomic_simulated.__globals__, "simulate_makespan", fail)

    batches = pack_by_count_atomic_simulated(tasks, width=16, count=32, workers=8)

    assert_all_tasks_packed_once(batches, tasks)
    assert_batch_metadata(batches, algorithm="pack_by_count_atomic_simulated", width=16)


def test_dependency_components_uses_caller_width_and_workers(monkeypatch) -> None:
    tasks = [
        task("a", width=2, duration=10.0),
        task("b", width=2, duration=5.0, dependencies=("a",)),
        task("c", width=1, duration=7.0),
        task("d", width=1, duration=3.0, dependencies=("c",)),
    ]

    original = pack_by_count_atomic_simulated.__globals__["cheap_makespan"]
    seen: list[tuple[int, int | None]] = []

    def wrapped_cheap_makespan(*args, **kwargs):
        seen.append((kwargs["width"], kwargs.get("workers")))
        return original(*args, **kwargs)

    monkeypatch.setitem(
        pack_by_count_atomic_simulated.__globals__, "cheap_makespan", wrapped_cheap_makespan
    )

    batches = pack_by_count_atomic_simulated(tasks, width=8, count=2, workers=3)

    assert_all_tasks_packed_once(batches, tasks)
    assert seen
    assert all(width == 8 for width, _ in seen)
    assert all(workers == 3 for _, workers in seen)


def test_large_pack_by_count_simulated_30000_validity() -> None:
    tasks = make_large_flat_tasks(30_000)

    batches = pack_by_count_simulated(tasks, width=16, count=64, workers=8)

    assert_all_tasks_packed_once(batches, tasks)
    assert_flat_batches_have_no_internal_dependencies(batches)
    assert len(batches) <= 64
    assert_batch_metadata(batches, algorithm="pack_by_count_simulated", width=16)


def test_large_pack_to_height_simulated_30000_validity() -> None:
    tasks = make_large_flat_tasks(30_000)

    batches = pack_to_height_simulated(tasks, width=16, height=5000.0, workers=8)

    assert_all_tasks_packed_once(batches, tasks)
    assert_flat_batches_have_no_internal_dependencies(batches)
    assert_batch_metadata(batches, algorithm="pack_to_height_simulated", width=16)


def test_large_pack_by_count_atomic_simulated_30000_validity() -> None:
    tasks = make_large_atomic_tasks(30_000)

    batches = pack_by_count_atomic_simulated(tasks, width=16, count=256, workers=8)

    assert_all_tasks_packed_once(batches, tasks)
    assert len(batches) <= 256
    assert_batch_metadata(batches, algorithm="pack_by_count_atomic_simulated", width=16)


def test_exact_simulator_still_works_after_packer_optimization() -> None:
    tasks = [
        task("a", width=2, duration=10.0),
        task("b", width=2, duration=5.0),
        task("c", width=1, duration=3.0, dependencies=("a",)),
    ]

    assert simulate_makespan(tasks, width=4, workers=None) == pytest.approx(13.0)
    assert simulate_makespan(tasks, width=4, workers=1) == pytest.approx(18.0)
