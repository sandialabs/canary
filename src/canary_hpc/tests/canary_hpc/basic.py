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
    return glob.glob(f".canary/sessions/*/batches/**/{pattern}", recursive=True)


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
import canary_pyt
canary_pyt.directives.keywords('long')
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


def write_mixed_tests(pass_names: list[str], fail_names: list[str], control_file: str) -> None:
    """Write passing tests and conditionally-failing tests governed by a control file."""
    for name in pass_names:
        with open(f"{name}.pyt", "w") as fh:
            fh.write(
                """\
import sys
import canary_pyt
canary_pyt.directives.keywords('long')
def test():
    pass
if __name__ == '__main__':
    sys.exit(test())
"""
            )
    for name in fail_names:
        with open(f"{name}.pyt", "w") as fh:
            fh.write(
                f"""\
import sys
import pathlib
import canary_pyt
canary_pyt.directives.keywords('long')
def test():
    if pathlib.Path({control_file!r}).read_text().strip() == "fail":
        sys.exit(1)
if __name__ == '__main__':
    sys.exit(test())
"""
            )


def test_hpc_rerun_not_pass_skips_passing_jobs(tmpdir):
    """Regression: --only=not_pass on a second HPC run must not re-execute passing jobs.

    First run:  4 passing tests + 4 failing tests in 2 batches.
    Second run (--only=not_pass, sentinel fixed): only the 4 previously-failing
    jobs should run.  The 4 passing jobs must keep their first-session results
    and must not acquire a new result row in the DB.
    """
    with working_dir(tmpdir.strpath, create=True):
        control = os.path.join(tmpdir.strpath, "control.txt")
        with open(control, "w") as fh:
            fh.write("fail")

        # 4 always-passing + 4 conditionally-failing tests → 2 batches of 4
        pass_names = [f"pass_{i}" for i in range(4)]
        fail_names = [f"fail_{i}" for i in range(4)]
        write_mixed_tests(pass_names, fail_names, control)

        hpc = CanaryCommand("hpc")

        # First run: all 8 tests run; 4 pass, 4 fail
        cp1 = hpc(
            "run",
            "-w",
            "--batch-spec=count=2",
            "--scheduler=shell",
            ".",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Don't assert returncode — we expect 4 failures

        session1_batches = glob.glob(".canary/sessions/*/batches/*/canary-out.txt")
        assert len(session1_batches) == 2, (
            f"Expected 2 batch output files after first run, got {len(session1_batches)}"
        )
        session1 = re.search(r"sessions/([^/]+)/", session1_batches[0]).group(1)

        # Record the DB state: note the session for each spec after run 1
        import sqlite3

        db_path = os.path.join(".canary", "workspace.sqlite3")
        conn = sqlite3.connect(db_path)
        rows_after_run1 = {
            row[0]: (row[1], row[2])  # spec_id → (session, category)
            for row in conn.execute(
                "SELECT spec_id, session, status_category FROM results"
            ).fetchall()
        }
        conn.close()

        assert sum(1 for _, (_, cat) in rows_after_run1.items() if cat == "PASS") == 4
        assert sum(1 for _, (_, cat) in rows_after_run1.items() if cat == "FAIL") == 4

        # Fix the failing tests
        with open(control, "w") as fh:
            fh.write("pass")

        # Second run: --only=not_pass — only the 4 failing jobs should re-run
        cp2 = hpc(
            "run",
            "--only=not_pass",
            "--batch-spec=count=2",
            "--scheduler=shell",
            ".",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert cp2.returncode == 0, (
            f"Second run failed (rc={cp2.returncode})\nstdout: {cp2.stdout}\nstderr: {cp2.stderr}"
        )

        # Check DB: passing jobs must still have session1 as their latest session.
        # If they were re-run, they'd have a new (later) session.
        conn = sqlite3.connect(db_path)
        rows_after_run2 = conn.execute(
            "SELECT spec_id, session, status_category FROM results"
        ).fetchall()
        conn.close()

        # Group by spec_id: keep only the latest session per spec
        latest: dict[str, tuple[str, str]] = {}
        for spec_id, session, category in rows_after_run2:
            if spec_id not in latest or session > latest[spec_id][0]:
                latest[spec_id] = (session, category)

        for spec_id, (sess, cat) in rows_after_run1.items():
            new_sess, new_cat = latest[spec_id]
            if cat == "PASS":
                # Passing job must not have been re-run: still in session1
                assert new_sess == session1, (
                    f"Passing job {spec_id[:12]} was re-run: "
                    f"session changed from {session1} to {new_sess}"
                )
            else:
                # Failing job must have been re-run: new session, now PASS
                assert new_sess != session1, (
                    f"Failing job {spec_id[:12]} was NOT re-run: still in session {new_sess}"
                )
                assert new_cat == "PASS", (
                    f"Failing job {spec_id[:12]} re-ran but is still {new_cat}"
                )


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
