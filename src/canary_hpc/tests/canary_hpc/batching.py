# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import pytest

from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir
from canary_hpc import batching

num_cases = 25
num_base_cases = 5


def generate_specs(generators, on_options=None):
    from _canary import generate

    g = generate.Generator(generators, workspace=Path.cwd(), on_options=on_options or [])
    specs = g.run()
    return specs


@pytest.fixture(scope="function")
def generate_files(tmpdir):
    workdir = tmpdir.strpath
    mkdirp(workdir)
    for name in "abcde":
        with open(f"{workdir}/{name}.pyt", "w") as fh:
            fh.write("import canary_pyt\n")
            fh.write("canary_pyt.directives.keywords('long')\n")
            fh.write(f"canary_pyt.directives.parameterize({name!r}, list(range(4)))\n")
            fh.write("canary_pyt.directives.aggregate()\n")
    yield workdir


def generate_jobs(dirname):
    import _canary.collect
    import _canary.job
    import _canary.testexec

    Dependency = _canary.job.Dependency

    generators = _canary.collect.find_generators_in_path(dirname)
    specs = generate_specs(generators)
    lookup = {}
    jobs = []
    for spec in specs:
        ws = _canary.testexec.ExecutionSpace(Path.cwd(), Path("foo"))
        deps = [Dependency(job=lookup[d.spec.id], when="on_success") for d in spec.dependencies]
        job = _canary.job.Job(spec=spec, workspace=ws, dependencies=deps)
        jobs.append(job)
        lookup[job.id] = job
    return jobs


def batching_spec(
    *,
    layout: str = "flat",
    nodes: str = "any",
    count: int | None = None,
    duration: float | None = None,
) -> batching.BatchingSpec:
    return batching.BatchingSpec.with_defaults(
        layout=layout, nodes=nodes, count=count, duration=duration
    )


def test_batch_n(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        jobs = generate_jobs(workdir)

        spec = batching_spec(layout="flat", nodes="any", count=5)
        batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

        assert len(batches) <= 5
        assert sum(len(batch) for batch in batches) == num_cases
        assert all(hasattr(batch, "estimated_runtime") for batch in batches)

        spec = batching_spec(layout="flat", nodes="any", count=batching.MAX_COUNT)
        batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

        assert len(batches) == num_cases
        assert sum(len(batch) for batch in batches) == num_cases


def test_batch_t(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        jobs = generate_jobs(workdir)

        spec = batching_spec(layout="flat", nodes="any", duration=15 * 60)
        batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

        assert sum(len(batch) for batch in batches) == num_cases
        assert all(batch.estimated_runtime <= 15 * 60 for batch in batches)

        spec = batching_spec(layout="flat", nodes="same", duration=15 * 60)
        batches = batching.batch_jobs(jobs=jobs, width=64, spec=spec)

        assert sum(len(batch) for batch in batches) == num_cases
        assert all(hasattr(batch, "estimated_runtime") for batch in batches)


def test_partition_jobs_flat_nodes_any(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="any", cpus_per_node=64
        )

        assert partitions
        assert sum(len(partition.jobs) for partition in partitions) == num_cases
        assert all(partition.width == partition.node_count * 64 for partition in partitions)

        # The generated composite base case structure should have at least one
        # topological level. Do not over-specify exact level count here.
        assert all(partition.key.startswith("layout=flat,nodes=any") for partition in partitions)


def test_partition_jobs_flat_nodes_same(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="same", cpus_per_node=64
        )

        assert partitions
        assert sum(len(partition.jobs) for partition in partitions) == num_cases
        assert all(partition.width == partition.node_count * 64 for partition in partitions)
        assert all(partition.key.startswith("layout=flat,nodes=same") for partition in partitions)

        for partition in partitions:
            node_counts = {max(1, len(job.required_resources())) for job in partition.jobs}
            assert node_counts == {partition.node_count}


def test_partition_jobs_atomic_requires_nodes_any(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

        with pytest.raises(ValueError, match="layout=atomic requires nodes=any"):
            batching.partition_jobs(jobs=jobs, layout="atomic", nodes="same", cpus_per_node=64)


def test_partition_jobs_atomic_nodes_any_single_partition(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

        partitions = batching.partition_jobs(
            jobs=jobs, layout="atomic", nodes="any", cpus_per_node=64
        )

        assert len(partitions) == 1
        assert len(partitions[0].jobs) == num_cases
        assert partitions[0].width == partitions[0].node_count * 64


def test_allocate_partition_counts_none(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)
        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="any", cpus_per_node=64
        )

        counts = batching.allocate_partition_counts(None, partitions)

        assert counts == [None for _ in partitions]


def test_allocate_partition_counts_max(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)
        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="any", cpus_per_node=64
        )

        counts = batching.allocate_partition_counts(batching.MAX_COUNT, partitions)

        assert counts == [batching.MAX_COUNT for _ in partitions]


def test_allocate_partition_counts_integer(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)
        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="any", cpus_per_node=64
        )

        count = len(partitions) + 3
        counts = batching.allocate_partition_counts(count, partitions)

        assert len(counts) == len(partitions)
        assert all(isinstance(c, int) for c in counts)
        assert sum(c for c in counts if isinstance(c, int)) <= count
        assert all(c >= 1 for c in counts if isinstance(c, int))


def test_allocate_partition_counts_insufficient(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)
        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="any", cpus_per_node=64
        )

        if len(partitions) <= 1:
            pytest.skip("Need more than one partition to test insufficient count")

        with pytest.raises(ValueError, match="insufficient"):
            batching.allocate_partition_counts(len(partitions) - 1, partitions)


def test_set_batch_dependencies_global(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

        partitions = batching.partition_jobs(
            jobs=jobs, layout="flat", nodes="any", cpus_per_node=64
        )
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


def test_partition_jobs_uses_resources_per_node_for_capacity(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

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


def test_batch_jobs_exact_final_estimate_metadata(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

        spec = batching_spec(layout="flat", nodes="any", count=2)
        batches = batching.batch_jobs(
            jobs=jobs, width=64, workers=None, spec=spec, exact_final_estimate=True
        )

        assert batches
        assert all(batch.schedule_metadata["exact_final_estimate"] is True for batch in batches)
        assert all(batch.schedule_metadata["simulated_runtime"] is not None for batch in batches)


def test_batch_jobs_preserves_schedule_metadata(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        jobs = generate_jobs(generate_files)

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

    counts = batching.allocate_partition_counts(30, partitions)

    assert sum(counts) == 30
    # Every tiny aggregate partition keeps a home (min 1)...
    assert all(c >= 1 for c in counts)
    # ...but the dominant partition claims the remaining budget.
    assert counts[0] == 30 - len(aggregates)
    assert all(c == 1 for c in counts[1:])


def test_allocate_partition_counts_proportional_across_large_partitions() -> None:
    partitions = [
        _FakePartition(2000, 2000 * 300.0 / 48),
        _FakePartition(1000, 1000 * 300.0 / 48),
        _FakePartition(500, 500 * 300.0 / 48),
    ]

    counts = batching.allocate_partition_counts(28, partitions)

    assert sum(counts) == 28
    # Allocation should be roughly proportional to load (2:1:0.5).
    assert counts[0] > counts[1] > counts[2]
    assert counts == [16, 8, 4]


def test_allocate_partition_counts_equal_partitions_are_balanced() -> None:
    partitions = [_FakePartition(100, 100.0) for _ in range(7)]

    counts = batching.allocate_partition_counts(30, partitions)

    assert sum(counts) == 30
    # Equal partitions should differ by at most one batch.
    assert max(counts) - min(counts) <= 1
