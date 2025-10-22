# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import os
import re

import pytest

import _canary.config
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


@pytest.fixture(scope="function", autouse=True)
def config(request):
    try:
        env_copy = os.environ.copy()
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        _canary.config._config = _canary.config.Config()
        yield
    except:
        os.environ.clear()
        os.environ.update(env_copy)


def test_batched(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import canary
canary.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        hpc = CanaryCommand("hpc")
        hpc.add_default_args("-r", "cpus=6", "-r", "gpus=0")
        cp = hpc("run", "-w", "--batch-spec=count=4", "--scheduler=shell", ".", debug=True)
        dirs = os.listdir("TestResults")
        expected = [".canary"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        files = glob.glob("TestResults/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob(
            "TestResults/.canary/canary_hpc/batches/**/canary-out.txt", recursive=True
        )
        assert len(files) == 4
        assert cp.returncode == 0


def test_batched_extra_args(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import canary
canary.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        hpc = CanaryCommand("hpc")
        hpc.add_default_args("-r", "cpus=6", "-r", "gpus=0")
        args = ["run", "-w", "--batch-spec=count:4", "--scheduler=shell"]
        args.append("--scheduler-args='-l place=scatter:excl,-q debug,-A XYZ123'")
        args.append(".")
        cp = hpc(*args)
        dirs = os.listdir("TestResults")
        expected = [".canary"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        files = glob.glob("TestResults/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob("TestResults/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
        found = 0
        for line in open(files[0]):
            if re.search(r"#\s*BASH:? -l place=scatter:excl", line):
                found += 1
            elif re.search(r"#\s*BASH:? -q debug", line):
                found += 1
            elif re.search(r"#\s*BASH:? -A XYZ123", line):
                found += 1
        assert found == 3
        if cp.returncode != 0:
            print(open(files[0], "r").read())
        assert len(files) == 4
        files = glob.glob(
            "TestResults/.canary/canary_hpc/batches/**/canary-out.txt", recursive=True
        )
        assert len(files) == 4
        if cp.returncode != 0:
            print(open(files[0], "r").read())
        assert cp.returncode == 0


def test_batched_legacy(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import canary
canary.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = CanaryCommand("run")
        run.add_default_args("-r", "cpus=6", "-r", "gpus=0")
        cp = run("-w", "-b", "spec=count:4", "-b", "backend=shell", ".")
        dirs = os.listdir("TestResults")
        expected = [".canary"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        files = glob.glob("TestResults/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob(
            "TestResults/.canary/canary_hpc/batches/**/canary-out.txt", recursive=True
        )
        assert len(files) == 4
        assert cp.returncode == 0


def test_batched_extra_args_legacy(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        for i in range(12):
            with open(f"test_{i}.pyt", "w") as fh:
                fh.write(
                    """\
import sys
import canary
canary.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
                )

        run = CanaryCommand("run")
        run.add_default_args("-r", "cpus=6", "-r", "gpus=0")
        args = ["-w", "-b", "spec=count:4", "-b", "scheduler=shell"]
        args.extend(["-b", "args='-l place=scatter:excl,-q debug,-A XYZ123'"])
        args.append(".")
        cp = run(*args)
        dirs = os.listdir("TestResults")
        expected = [".canary"] + [f"test_{i}" for i in range(12)]
        assert sorted(expected) == sorted(dirs)
        files = glob.glob("TestResults/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
        assert len(files) == 4
        files = glob.glob("TestResults/.canary/canary_hpc/batches/**/canary-inp.sh", recursive=True)
        found = 0
        print(open(files[0]).read())
        for line in open(files[0]):
            if re.search(r"#\s*BASH:? -l place=scatter:excl", line):
                found += 1
            elif re.search(r"#\s*BASH:? -q debug", line):
                found += 1
            elif re.search(r"#\s*BASH:? -A XYZ123", line):
                found += 1
        assert found == 3
        if cp.returncode != 0:
            print(open(files[0], "r").read())
        assert len(files) == 4
        files = glob.glob(
            "TestResults/.canary/canary_hpc/batches/**/canary-out.txt", recursive=True
        )
        assert len(files) == 4
        if cp.returncode != 0:
            print(open(files[0], "r").read())
        assert cp.returncode == 0
