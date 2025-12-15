# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
from pathlib import Path

import pytest

from _canary.util.filesystem import mkdirp
from _canary.util.filesystem import working_dir
from canary_hpc import batching
from canary_hpc.binpack import ONE_PER_BIN

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


def generate_testcases(dirname):
    import _canary.testcase
    import _canary.testexec
    import _canary.workspace

    generators = _canary.workspace.find_generators_in_path(dirname)
    specs = generate_specs(generators)
    lookup = {}
    cases = []
    for spec in specs:
        ws = _canary.testexec.ExecutionSpace(Path.cwd(), Path("foo"))
        deps = [lookup[d.id] for d in spec.dependencies]
        case = _canary.testcase.TestCase(spec=spec, workspace=ws, dependencies=deps)
        cases.append(case)
        lookup[case.id] = case
    return cases


def test_batch_n(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        cases = generate_testcases(workdir)
        kwds = {"count": 5, "duration": None, "nodes": "any", "layout": "flat"}
        batches = batching.batch_testcases(cases=cases, **kwds)
        assert len(batches) == 5
        assert sum(len(_) for _ in batches) == num_cases
        kwds = {"count": ONE_PER_BIN, "duration": None, "nodes": "any", "layout": "flat"}
        batches = batching.batch_testcases(cases=cases, **kwds)
        assert len(batches) == num_cases


def test_batch_t(generate_files, tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        workdir = generate_files
        cases = generate_testcases(workdir)
        kwds = {"count": None, "duration": 15 * 60, "nodes": "any", "layout": "flat"}
        batches = batching.batch_testcases(cases=cases, **kwds)
        assert sum(len(_) for _ in batches) == num_cases
        kwds = {"count": None, "duration": 15 * 60, "nodes": "same", "layout": "flat"}
        batches = batching.batch_testcases(cases=cases, **kwds)
        assert len(batches) == num_cases
