# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.finder
from _canary.util.filesystem import mkdirp
from canary_hpc import partitioning

num_cases = 25
num_base_cases = 5


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


def test_partition_n(generate_files):
    workdir = generate_files
    f = _canary.finder.Finder()
    f.add(workdir)
    f.prepare()
    files = f.discover()
    cases = _canary.finder.generate_test_cases(files)
    assert len([c for c in cases if c.status != "masked"]) == num_cases
    partitions = partitioning.partition_n(cases, n=5)
    assert len(partitions) == 5
    assert sum(len(_) for _ in partitions) == num_cases
    partitions = partitioning.partition_n(cases, n=partitioning.ONE_PER_BATCH)
    assert len(partitions) == num_cases


def test_partition_t(generate_files):
    workdir = generate_files
    f = _canary.finder.Finder()
    f.add(workdir)
    f.prepare()
    files = f.discover()
    cases = _canary.finder.generate_test_cases(files)
    assert len([c for c in cases if c.status != "masked"]) == num_cases
    partitions = partitioning.partition_t(cases, t=15 * 60)  # 5x long test case duration
    assert sum(len(_) for _ in partitions) == num_cases
    partitions = partitioning.partition_t(cases, t=15 * 60, nodes="match")
    assert sum(len(_) for _ in partitions) == num_cases
