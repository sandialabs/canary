# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import os
import re
import subprocess

import pytest

import _canary.config
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand


@pytest.fixture(scope="function", autouse=True)
def config(request):
    env_copy = os.environ.copy()
    try:
        os.environ.pop("CANARYCFG64", None)
        os.environ["CANARY_DISABLE_KB"] = "1"
        _canary.config._config = _canary.config.Config()
        yield
    finally:
        os.environ.clear()
        os.environ.update(env_copy)


def glob_files_in_session(pattern):
    return glob.glob(f".canary/cache/canary-hpc/batches/**/{pattern}", recursive=True)


def assert_success(cp: subprocess.CompletedProcess) -> None:
    if cp.returncode == 0:
        return

    print(f"canary command failed with returncode={cp.returncode}")

    stdout = getattr(cp, "stdout", None)
    stderr = getattr(cp, "stderr", None)
    if stdout:
        print("\n--- stdout ---")
        print(stdout)
    if stderr:
        print("\n--- stderr ---")
        print(stderr)

    for file in glob_files_in_session("canary-out.txt"):
        print(f"\n--- {file} ---")
        try:
            print(open(file).read())
        except OSError as e:
            print(f"failed to read {file}: {e}")

    log = ".canary/logs/canary.0.log"
    if os.path.exists(log):
        print(f"\n--- {log} ---")
        try:
            print(open(log).read())
        except OSError as e:
            print(f"failed to read {log}: {e}")

    assert cp.returncode == 0


def write_basic_tests(n: int = 12) -> None:
    for i in range(n):
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


def write_one_basic_test() -> None:
    with open("test_0.pyt", "w") as fh:
        fh.write(
            """\
import sys
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
        )


def assert_testresults_contains_basic_tests(n: int = 12) -> None:
    dirs = os.listdir("TestResults")
    expected = [".canary-view.json"] + [f"test_{i}" for i in range(n)]
    assert sorted(expected) == sorted(dirs)


def assert_batch_files(expected_count: int) -> None:
    files = glob_files_in_session("*.sh")
    assert len(files) == expected_count

    files = glob_files_in_session("canary-out.txt")
    assert len(files) == expected_count


def assert_scheduler_args_written(file: str) -> None:
    found = 0
    for line in open(file):
        if re.search(r"#\s*BASH:? -l place=scatter:excl", line):
            found += 1
        elif re.search(r"#\s*BASH:? -q debug", line):
            found += 1
        elif re.search(r"#\s*BASH:? -A XYZ123", line):
            found += 1
    assert found == 3


def test_batched(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        write_basic_tests(12)

        hpc = CanaryCommand("hpc")
        cp = hpc("run", "-w", "--batch-spec=count=4", "--scheduler=shell", ".", debug=True)
        assert_success(cp)

        assert_testresults_contains_basic_tests(12)
        assert_batch_files(expected_count=4)


def test_batched_extra_args(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        write_basic_tests(12)

        hpc = CanaryCommand("hpc")
        args = ["run", "-w", "--batch-spec=count:4", "--scheduler=shell"]
        args.append("--scheduler-args='-l place=scatter:excl,-q debug,-A XYZ123'")
        args.append(".")
        cp = hpc(*args)
        assert_success(cp)

        assert_testresults_contains_basic_tests(12)

        files = glob_files_in_session("*.sh")
        assert len(files) == 4
        assert_scheduler_args_written(files[0])

        files = glob_files_in_session("canary-out.txt")
        assert len(files) == 4


def test_batched_legacy(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        write_basic_tests(12)

        run = CanaryCommand("run")
        cp = run("-w", "-b", "spec=count:4", "-b", "backend=shell", ".")
        assert_success(cp)

        assert_testresults_contains_basic_tests(12)
        assert_batch_files(expected_count=4)


def test_batched_extra_args_legacy(tmpdir):
    # add long keyword so that batches have a length to minimize when partitioning
    with working_dir(tmpdir.strpath, create=True):
        write_basic_tests(12)

        run = CanaryCommand("run")
        args = ["-w", "-b", "spec=count:4", "-b", "scheduler=shell"]
        args.extend(["-b", "args='-l place=scatter:excl,-q debug,-A XYZ123'"])
        args.append(".")
        cp = run(*args)
        assert_success(cp)

        assert_testresults_contains_basic_tests(12)

        files = glob_files_in_session("*.sh")
        assert len(files) == 4
        assert_scheduler_args_written(files[0])

        files = glob_files_in_session("canary-out.txt")
        assert len(files) == 4


def test_hpc_rejects_canary_resource_overrides(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write_one_basic_test()

        hpc = CanaryCommand("hpc")
        hpc.add_default_args("-r", "cpus=6")
        cp = hpc(
            "run",
            "-w",
            "--batch-spec=count=1",
            "--scheduler=shell",
            ".",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )

        assert cp.returncode != 0
        assert "Resource-pool overrides are not allowed" in cp.stderr
        assert not os.path.exists("TestResults")


def test_hpc_rejects_canary_resource_overrides_legacy(tmpdir):
    with working_dir(tmpdir.strpath, create=True):
        write_one_basic_test()

        run = CanaryCommand("run")
        run.add_default_args("-r", "cpus=6")
        cp = run(
            "-w",
            "-b",
            "spec=count:1",
            "-b",
            "backend=shell",
            ".",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )

        assert cp.returncode != 0
        assert "Resource-pool overrides are not allowed" in cp.stderr
        assert not os.path.exists("TestResults")
