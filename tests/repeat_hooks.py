# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Integration tests for the built-in ``canary_runtest`` repeat hooks.

These exercise the *real* hook chain -- ``Workspace.run`` -> ``canary_runtests``
-> ``JobExecutor`` -> ``pm.canary_runtest`` (the ``wrapper`` runner plus the
non-wrapper post-run impls in ``_canary/hooks.py``) -- rather than unit-testing
a predicate in isolation.  They verify that a failed case is actually
re-executed within a single session when the corresponding repeat option is set,
which is the behavior the smash-python ``--smash-repeat-on-gpu-error`` hook
relies on and copies.

Each test drives a ``.pyt`` case whose pass/fail outcome is controlled by a
counter file living at the workspace root (outside the case workspace, so it
survives ``Job.restore_workspace()`` between rerun attempts).
"""

import argparse
from pathlib import Path

import canary
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def create_workspace(root: Path) -> tuple[Workspace, list[canary.JobSpec]]:
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        return workspace, specs


def run_specs(
    workspace: Workspace,
    specs: list[canary.JobSpec],
    *,
    options: dict | None = None,
    only: str = "all",
):
    with working_dir(workspace.root), canary.config.override() as cfg:
        cfg.options = argparse.Namespace(**(options or {}))
        return workspace.run(specs, only=only)


def jobs_by_name(workspace: Workspace) -> dict[str, canary.Job]:
    return {job.name: job for job in workspace.load_jobs()}


def _counter_case(counter: Path, *, fail_while_lt: int) -> str:
    """A .pyt body that increments *counter* each run and fails while the

    post-increment count is < ``fail_while_lt`` (i.e. fails on the first
    ``fail_while_lt - 1`` runs, then passes)."""
    return f"""\
import pathlib
import sys

import canary

counter = pathlib.Path({str(counter)!r})


def test():
    n = int(counter.read_text()) if counter.exists() else 0
    n += 1
    counter.write_text(str(n))
    if n < {fail_while_lt}:
        raise canary.TestFailed(f"attempt {{n}} deliberately failing")


if __name__ == "__main__":
    sys.exit(test())
"""


def _timeout_then_pass_case(counter: Path) -> str:
    """First run sleeps past a tiny timeout; subsequent runs pass quickly."""
    return f"""\
import pathlib
import sys
import time

import canary_pyt

canary_pyt.directives.timeout("2s")

counter = pathlib.Path({str(counter)!r})


def test():
    n = int(counter.read_text()) if counter.exists() else 0
    n += 1
    counter.write_text(str(n))
    if n == 1:
        time.sleep(30)


if __name__ == "__main__":
    sys.exit(test())
"""


def test_repeat_until_pass_reruns_failed_case_until_it_passes(tmp_path):
    root = tmp_path / "repeat-until-pass"
    root.mkdir()
    counter = root / "counter.txt"

    # Fails on attempt 1, passes on attempt 2.
    write(root / "flaky.pyt", _counter_case(counter, fail_while_lt=2))

    workspace, specs = create_workspace(root)
    session = run_specs(workspace, specs, options={"repeat_until_pass": 3})
    jobs = jobs_by_name(workspace)

    # The retry hook must have re-run the case a second time and it must
    # ultimately succeed within the single session.
    assert session.returncode == 0
    assert jobs["flaky"].status.is_success()
    assert int(counter.read_text()) == 2


def test_repeat_until_pass_gives_up_after_n_attempts(tmp_path):
    root = tmp_path / "repeat-until-pass-exhausted"
    root.mkdir()
    counter = root / "counter.txt"

    # Requires 5 attempts to pass, but we only allow 2 additional retries (3 total).
    write(root / "always.pyt", _counter_case(counter, fail_while_lt=5))

    workspace, specs = create_workspace(root)
    session = run_specs(workspace, specs, options={"repeat_until_pass": 2})
    jobs = jobs_by_name(workspace)

    # Initial run + 2 retries == 3 executions, then it gives up still-failed.
    assert session.returncode != 0
    assert jobs["always"].status.outcome.name == "FAILED"
    assert int(counter.read_text()) == 3


def test_repeat_until_pass_does_not_rerun_a_passing_case(tmp_path):
    root = tmp_path / "repeat-until-pass-noop"
    root.mkdir()
    counter = root / "counter.txt"

    # Passes on the first attempt.
    write(root / "good.pyt", _counter_case(counter, fail_while_lt=1))

    workspace, specs = create_workspace(root)
    session = run_specs(workspace, specs, options={"repeat_until_pass": 3})
    jobs = jobs_by_name(workspace)

    assert session.returncode == 0
    assert jobs["good"].status.is_success()
    # Ran exactly once -- a passing case is never retried.
    assert int(counter.read_text()) == 1


def test_repeat_after_timeout_reruns_timed_out_case(tmp_path):
    root = tmp_path / "repeat-after-timeout"
    root.mkdir()
    counter = root / "counter.txt"

    write(root / "slow.pyt", _timeout_then_pass_case(counter))

    workspace, specs = create_workspace(root)
    session = run_specs(workspace, specs, options={"repeat_after_timeout": 2})
    jobs = jobs_by_name(workspace)

    assert session.returncode == 0
    assert jobs["slow"].status.is_success()
    assert int(counter.read_text()) == 2


def test_repeat_until_fail_reruns_passing_case_and_stops_on_failure(tmp_path):
    root = tmp_path / "repeat-until-fail"
    root.mkdir()
    counter = root / "counter.txt"

    # Passes on attempts 1 and 2, then fails on attempt 3.
    write(root / "eventually.pyt", _fail_on_attempt(counter, fail_on=3))

    workspace, specs = create_workspace(root)
    session = run_specs(workspace, specs, options={"repeat_until_fail": 5})
    jobs = jobs_by_name(workspace)

    # repeat-until-fail requires N passes; it stops as soon as one attempt fails.
    assert session.returncode != 0
    assert jobs["eventually"].status.outcome.name == "FAILED"
    assert int(counter.read_text()) == 3


def _fail_on_attempt(counter: Path, *, fail_on: int) -> str:
    """A .pyt body that passes until attempt ``fail_on``, which fails."""
    return f"""\
import pathlib
import sys

import canary

counter = pathlib.Path({str(counter)!r})


def test():
    n = int(counter.read_text()) if counter.exists() else 0
    n += 1
    counter.write_text(str(n))
    if n == {fail_on}:
        raise canary.TestFailed(f"attempt {{n}} deliberately failing")


if __name__ == "__main__":
    sys.exit(test())
"""
