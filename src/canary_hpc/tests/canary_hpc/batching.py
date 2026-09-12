# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for canary_hpc.batching.

The generate_files fixture + generate_jobs() originally wrote .pyt files and
ran them through the full generator/collect pipeline (~0.4s per test, ~7s total
for the 17 tests that used it).  Replaced with make_jobs() which builds Job
objects directly — the same structure (5 families × 4 leaf + 1 aggregate = 25
jobs) without any file I/O or subprocess overhead.
"""

import hashlib
from pathlib import Path

import pytest

from canary_hpc import batching

num_cases = 25
num_base_cases = 5


# ---------------------------------------------------------------------------
# Job factory — no file I/O, no subprocess
# ---------------------------------------------------------------------------


def _job_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def make_jobs(tmp_path: Path, cpus: int = 1, nodes: int = 1) -> list:
    """Build 25 Job objects (5 families × 4 leaf + 1 aggregate) directly.

    Structure mirrors the old generate_files/generate_jobs output:
      - 5 families named "a"–"e"
      - each has 4 leaf variants (param=0..3) with 'long' keyword
      - each family has 1 aggregate that depends on all 4 leafs
    Total: 25 jobs (20 leaf + 5 aggregates).
    """
    import _canary.job
    import _canary.jobspec
    import _canary.testexec

    Dependency = _canary.job.Dependency
    Job = _canary.job.Job
    JobSpec = _canary.jobspec.JobSpec
    ExecutionSpace = _canary.testexec.ExecutionSpace

    ws = ExecutionSpace(tmp_path, Path("session"))
    lookup: dict[str, Job] = {}  # type: ignore[valid-type]
    jobs: list[Job] = []  # type: ignore[valid-type]

    for family in "abcde":
        leaf_jobs: list[Job] = []  # type: ignore[valid-type]

        for param in range(4):
            name = f"{family}.{family}={param}"
            spec = JobSpec(
                file_root=tmp_path,
                file_path=tmp_path / f"{family}.pyt",
                family=family,
                id=_job_id(name),
                parameters={family: param, "cpus": cpus, "nodes": nodes},
                keywords=["long"],
                timeout=300.0,
            )
            job = Job(spec=spec, workspace=ws)
            lookup[job.id] = job
            leaf_jobs.append(job)
            jobs.append(job)

        # Aggregate job that depends on all 4 leafs.
        agg_name = f"{family}.aggregate"
        agg_spec = JobSpec(
            file_root=tmp_path,
            file_path=tmp_path / f"{family}.pyt",
            family=f"{family}_aggregate",
            id=_job_id(agg_name),
            keywords=["long"],
            timeout=30.0,
        )
        deps = [Dependency(job=leaf, when="on_success") for leaf in leaf_jobs]
        agg_job = Job(spec=agg_spec, workspace=ws, dependencies=deps)
        lookup[agg_job.id] = agg_job
        jobs.append(agg_job)

    return jobs


def batching_spec(
    *,
    layout: str = "flat",
    nodes: str = "any",
    count: int | None = None,
    duration: float | None = None,
) -> batching.BatchingSpec:
    return batching.BatchingSpec.with_defaults(
        layout=layout,  # type: ignore[arg-type]
        nodes=nodes,  # type: ignore[arg-type]
        count=count,
        duration=duration,
    )


def test_with_defaults_count_implies_nodes_any() -> None:
    # When count is given without an explicit nodes value, nodes defaults to
    # "any" so the count is honoured as a global budget across mixed node counts.
    spec = batching.BatchingSpec.with_defaults(count=4)
    assert spec.node_policy == "any"
    assert spec.count == 4


def test_with_defaults_duration_implies_nodes_same() -> None:
    # When a duration target is given without an explicit nodes value, nodes
    # defaults to "same" (allocations sized exactly to their jobs).
    spec = batching.BatchingSpec.with_defaults(duration=1800.0)
    assert spec.node_policy == "same"


def test_with_defaults_explicit_nodes_same_with_count_respected() -> None:
    # An explicit nodes=same overrides the count-implies-any default.
    spec = batching.BatchingSpec.with_defaults(count=4, nodes="same")
    assert spec.node_policy == "same"
    assert spec.count == 4


def test_with_defaults_no_args_duration_nodes_same() -> None:
    # Default with no args: duration target, nodes=same.
    spec = batching.BatchingSpec.with_defaults()
    assert spec.node_policy == "same"
    assert spec.duration is not None


def test_batch_n(tmp_path):
    jobs = make_jobs(tmp_path)

    spec = batching_spec(layout="flat", nodes="any", count=5)
    batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

    assert len(batches) <= 5
    assert sum(len(batch) for batch in batches) == num_cases
    assert all(hasattr(batch, "estimated_runtime") for batch in batches)

    spec = batching_spec(layout="flat", nodes="any", count=batching.MAX_COUNT)
    batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

    assert len(batches) == num_cases
    assert sum(len(batch) for batch in batches) == num_cases


def test_batch_t(tmp_path):
    jobs = make_jobs(tmp_path)

    spec = batching_spec(layout="flat", nodes="any", duration=15 * 60)
    batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

    assert sum(len(batch) for batch in batches) == num_cases
    assert all(batch.estimated_runtime <= 15 * 60 for batch in batches)

    spec = batching_spec(layout="flat", nodes="same", duration=15 * 60)
    batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

    assert sum(len(batch) for batch in batches) == num_cases
    assert all(hasattr(batch, "estimated_runtime") for batch in batches)


def test_partition_jobs_flat_nodes_any(tmp_path):
    jobs = make_jobs(tmp_path)

    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="any", cpus_per_node=64)

    assert partitions
    assert sum(len(partition.jobs) for partition in partitions) == num_cases
    assert all(partition.width == partition.node_count * 64 for partition in partitions)
    assert all(partition.key.startswith("layout=flat,nodes=any") for partition in partitions)


def test_partition_jobs_flat_nodes_same(tmp_path):
    jobs = make_jobs(tmp_path)

    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="same", cpus_per_node=64)

    assert partitions
    assert sum(len(partition.jobs) for partition in partitions) == num_cases
    assert all(partition.width == partition.node_count * 64 for partition in partitions)
    assert all(partition.key.startswith("layout=flat,nodes=same") for partition in partitions)

    for partition in partitions:
        node_counts = {max(1, len(job.required_resources())) for job in partition.jobs}
        assert node_counts == {partition.node_count}


def test_partition_jobs_atomic_requires_nodes_any(tmp_path):
    jobs = make_jobs(tmp_path)

    with pytest.raises(ValueError, match="layout=atomic requires nodes=any"):
        batching.partition_jobs(jobs=jobs, layout="atomic", nodes="same", cpus_per_node=64)


def test_partition_jobs_atomic_nodes_any_single_partition(tmp_path):
    jobs = make_jobs(tmp_path)

    partitions = batching.partition_jobs(jobs=jobs, layout="atomic", nodes="any", cpus_per_node=64)

    assert len(partitions) == 1
    assert len(partitions[0].jobs) == num_cases
    assert partitions[0].width == partitions[0].node_count * 64


def test_allocate_partition_counts_none(tmp_path):
    jobs = make_jobs(tmp_path)
    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="any", cpus_per_node=64)

    counts = batching.allocate_partition_counts(None, partitions)

    assert counts == [None for _ in partitions]


def test_allocate_partition_counts_max(tmp_path):
    jobs = make_jobs(tmp_path)
    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="any", cpus_per_node=64)

    counts = batching.allocate_partition_counts(batching.MAX_COUNT, partitions)

    assert counts == [batching.MAX_COUNT for _ in partitions]


def test_allocate_partition_counts_integer(tmp_path):
    jobs = make_jobs(tmp_path)
    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="any", cpus_per_node=64)

    count = len(partitions) + 3
    counts = batching.allocate_partition_counts(count, partitions)

    assert len(counts) == len(partitions)
    assert all(isinstance(c, int) for c in counts)
    assert sum(c for c in counts if isinstance(c, int)) <= count
    assert all(c >= 1 for c in counts if isinstance(c, int))


def test_allocate_partition_counts_insufficient(tmp_path):
    jobs = make_jobs(tmp_path)
    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="any", cpus_per_node=64)

    if len(partitions) <= 1:
        pytest.skip("Need more than one partition to test insufficient count")

    with pytest.raises(ValueError, match="insufficient"):
        batching.allocate_partition_counts(len(partitions) - 1, partitions)


def test_set_batch_dependencies_global(tmp_path):
    jobs = make_jobs(tmp_path)

    partitions = batching.partition_jobs(jobs=jobs, layout="flat", nodes="any", cpus_per_node=64)
    counts = batching.allocate_partition_counts(None, partitions)

    specs = []
    for partition, count in zip(partitions, counts):
        if count is None:
            spec = batching_spec(layout="flat", nodes="any", duration=15 * 60)
        else:
            spec = batching_spec(layout="flat", nodes="any", count=count)

        specs.extend(batching.batch_jobs(jobs=partition.jobs, width=partition.width, spec=spec))

    batching.set_batch_dependencies(specs)

    assert sum(len(spec.jobs) for spec in specs) == num_cases

    # Ensure all dependency references point to known specs.
    spec_ids = {spec.id for spec in specs}
    for spec in specs:
        for dep in spec.dependencies:
            assert dep.id in spec_ids


def test_partition_jobs_uses_resources_per_node_for_capacity(tmp_path):
    jobs = make_jobs(tmp_path)

    partitions = batching.partition_jobs(
        jobs=jobs,
        layout="flat",
        nodes="any",
        cpus_per_node=64,
        resources_per_node={"cpus": 64, "gpus": 4},
    )

    assert partitions
    for partition in partitions:
        assert partition.resource_capacity["cpus"] == partition.width
        assert partition.resource_capacity["gpus"] == 4 * partition.node_count


def test_batch_jobs_exact_final_estimate_metadata(tmp_path):
    jobs = make_jobs(tmp_path)

    spec = batching_spec(layout="flat", nodes="any", count=2)
    batches = batching.batch_jobs(
        jobs=jobs, width=64, workers=None, spec=spec, exact_final_estimate=True
    )

    assert batches
    assert all(batch.schedule_metadata["exact_final_estimate"] is True for batch in batches)
    assert all(batch.schedule_metadata["simulated_runtime"] is not None for batch in batches)


def test_batch_jobs_preserves_schedule_metadata(tmp_path):
    jobs = make_jobs(tmp_path)

    spec = batching_spec(layout="flat", nodes="any", count=2)
    batches = batching.batch_jobs(
        jobs=jobs,
        width=64,
        workers=2,
        spec=spec,
        resource_capacity={"cpus": 64, "gpus": 4},
        node_count=1,
        exact_final_estimate=False,
    )

    assert batches

    for batch in batches:
        metadata = batch.schedule_metadata

        assert metadata["estimated_runtime"] == batch.estimated_runtime
        assert metadata["width"] == 64
        assert metadata["workers"] == 2
        assert metadata["resource_capacity"] == {"cpus": 64, "gpus": 4}
        assert metadata["node_count"] == 1
        assert metadata["exact_final_estimate"] is False
        assert "cheap_runtime" in metadata
        assert "simulated_runtime" in metadata


class _FakePartition:
    def __init__(self, njobs: int, weight: float, node_count: int = 1) -> None:
        self.jobs = list(range(njobs))
        self.weight = weight
        self.node_count = node_count


def test_allocate_partition_counts_balances_dominant_partition() -> None:
    # A large independent partition alongside several tiny (e.g. aggregate)
    # partitions must not be starved: the dominant partition should receive the
    # bulk of the count budget rather than losing batches to per-partition
    # minimums.  Regression test for the lopsided allocation that produced a
    # single enormous batch alongside many single-job batches.
    dominant = _FakePartition(5000, 5000 * 300.0 / 48)
    aggregates = [_FakePartition(2, 2 * 5.0 / 48) for _ in range(14)]
    partitions = [dominant, *aggregates]

    counts = batching.allocate_partition_counts(30, partitions)  # type: ignore[arg-type]

    assert sum(c for c in counts if c is not None) == 30
    # Every tiny aggregate partition keeps a home (min 1)...
    assert all(c >= 1 for c in counts if c is not None)
    # ...but the dominant partition claims the remaining budget.
    assert counts[0] == 30 - len(aggregates)
    assert all(c == 1 for c in counts[1:] if c is not None)


def test_allocate_partition_counts_proportional_across_large_partitions() -> None:
    partitions = [
        _FakePartition(2000, 2000 * 300.0 / 48),
        _FakePartition(1000, 1000 * 300.0 / 48),
        _FakePartition(500, 500 * 300.0 / 48),
    ]

    counts = batching.allocate_partition_counts(28, partitions)  # type: ignore[arg-type]

    assert sum(c for c in counts if c is not None) == 28
    # Allocation should be roughly proportional to load (2:1:0.5).
    assert counts[0] > counts[1] > counts[2]  # type: ignore[operator]
    assert counts == [16, 8, 4]


def test_allocate_partition_counts_equal_partitions_are_balanced() -> None:
    partitions = [_FakePartition(100, 100.0) for _ in range(7)]

    counts = batching.allocate_partition_counts(30, partitions)  # type: ignore[arg-type]

    assert sum(c for c in counts if c is not None) == 30
    # Equal partitions should differ by at most one batch.
    assert max(c for c in counts if c is not None) - min(c for c in counts if c is not None) <= 1
