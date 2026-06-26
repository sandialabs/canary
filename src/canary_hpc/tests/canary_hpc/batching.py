# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir
from canary_hpc import batching
from canary_hpc.binpack import BatchMode

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
        kwds = {"count": 5, "duration": None, "nodes": "any", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)
        assert len(batches) == 5
        assert sum(len(_) for _ in batches) == num_cases
        kwds = {"count": BatchMode.ONE_PER_BIN, "duration": None, "nodes": "any", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)
        assert len(batches) == num_cases


def test_batch_t(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        jobs = generate_jobs(workdir)
        kwds = {"count": None, "duration": 15 * 60, "nodes": "any", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)
        assert sum(len(_) for _ in batches) == num_cases
        kwds = {"count": None, "duration": 15 * 60, "nodes": "same", "layout": "flat"}
        batches = batching.batch_jobs(jobs=jobs, **kwds)
        assert len(batches) == num_cases
