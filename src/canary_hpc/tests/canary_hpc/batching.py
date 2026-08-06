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
            fh.write("import canary\n")
            fh.write("canary.directives.keywords('long')\n")
            fh.write(f"canary.directives.parameterize({name!r}, list(range(4)))\n")
            fh.write("canary.directives.generate_composite_base_case()\n")
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


def test_batch_n(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        jobs = generate_jobs(workdir)

        kwds = {"width": 64, "count": 5, "duration": None, "nodes": "any", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)

        assert len(batches) <= 5
        assert sum(len(batch) for batch in batches) == num_cases
        assert all(hasattr(batch, "estimated_runtime") for batch in batches)

        kwds = {"width": 64, "count": "max", "duration": None, "nodes": "any", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)

        assert len(batches) == num_cases
        assert sum(len(batch) for batch in batches) == num_cases


def test_batch_t(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        jobs = generate_jobs(workdir)

        kwds = {"width": 64, "count": None, "duration": 15 * 60, "nodes": "any", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)

        assert sum(len(batch) for batch in batches) == num_cases
        assert all(batch.estimated_runtime <= 15 * 60 for batch in batches)

        kwds = {"width": 64, "count": None, "duration": 15 * 60, "nodes": "same", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)

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
        # topological level.  Do not over-specify exact level count here.
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

        counts = batching.allocate_partition_counts("max", partitions)

        assert counts == ["max" for _ in partitions]


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
            specs.extend(
                batching.batch_jobs(
                    jobs=partition.jobs,
                    width=partition.width,
                    count=count,
                    duration=15 * 60,
                    nodes="any",
                    layout="flat",
                )
            )

        batching.set_batch_dependencies(specs)

        assert sum(len(spec.jobs) for spec in specs) == num_cases

        # Ensure all dependency references point to known specs.
        spec_ids = {spec.id for spec in specs}
        for spec in specs:
            for dep in spec.dependencies:
                assert dep.id in spec_ids
