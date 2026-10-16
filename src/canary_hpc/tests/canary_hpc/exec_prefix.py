# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""``--exec-prefix`` with ``canary hpc run``: forwarded to each batch's ``canary hpc exec``."""

import glob
import os
from pathlib import Path

from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand

BODY = """\
import os
import sys

def test():
    with open("out.txt", "w") as fh:
        fh.write(os.getcwd())
    return 0

if __name__ == "__main__":
    sys.exit(test())
"""


def _write_tests(n: int) -> None:
    for i in range(n):
        Path(f"test_{i}.pyt").write_text(BODY)


def _check_jobs_ran_below_prefix(n: int, prefix: Path) -> None:
    sessions = sorted(Path(".canary/sessions").iterdir())
    session = sessions[-1]
    for i in range(n):
        job_dir = session / f"test_{i}"
        # Executed below the prefix by the batch process ...
        ran_in = Path((job_dir / "out.txt").read_text())
        assert ran_in.is_relative_to(prefix / "canary"), ran_in
        assert ran_in.name == f"test_{i}"
        # ... and the results were copied back to the session directory.
        assert (job_dir / "canary-out.txt").exists()
        assert str(prefix) not in (job_dir / "testcase.lock").read_text()
        # The results view points at the session directory.
        assert Path(os.readlink(Path("TestResults") / f"test_{i}")) == job_dir.absolute()


def _batch_scripts() -> list[str]:
    return glob.glob(".canary/sessions/*/hpc.batches/**/*.sh", recursive=True)


def test_hpc_run_forwards_exec_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("FAST_ROOT", str(tmp_path))
    prefix = tmp_path / "fast"
    src = tmp_path / "src"
    with working_dir(str(src), create=True):
        _write_tests(4)
        hpc = CanaryCommand("hpc")
        # Quoted env var: expanded by the batch process, not the parent.
        cp = hpc(
            "run",
            "-w",
            "--batch-spec=count:2",
            "--backend=shell",
            "--exec-prefix=$FAST_ROOT/fast",
            ".",
        )
        assert cp.returncode == 0, cp.stdout
        scripts = _batch_scripts()
        assert len(scripts) == 2
        for script in scripts:
            assert "'--exec-prefix=$FAST_ROOT/fast'" in Path(script).read_text()
        _check_jobs_ran_below_prefix(4, prefix)


def test_legacy_run_forwards_exec_prefix(tmp_path):
    prefix = tmp_path / "fast"
    src = tmp_path / "src"
    with working_dir(str(src), create=True):
        _write_tests(2)
        run = CanaryCommand("run")
        cp = run("-w", "-b", "spec=count:1", "-b", "backend=shell", f"--exec-prefix={prefix}", ".")
        assert cp.returncode == 0, cp.stdout
        _check_jobs_ran_below_prefix(2, prefix)


def test_hpc_run_without_exec_prefix(tmp_path):
    src = tmp_path / "src"
    with working_dir(str(src), create=True):
        _write_tests(1)
        hpc = CanaryCommand("hpc")
        cp = hpc("run", "-w", "--batch-spec=count:1", "--backend=shell", ".")
        assert cp.returncode == 0, cp.stdout
        for script in _batch_scripts():
            assert "--exec-prefix" not in Path(script).read_text()
        session = sorted(Path(".canary/sessions").iterdir())[-1]
        ran_in = Path((session / "test_0" / "out.txt").read_text())
        assert ran_in == (session / "test_0").absolute()
