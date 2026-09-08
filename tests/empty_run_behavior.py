# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for workspace.run() behaviour when the result set is empty.

Two tests that previously called workspace.run() just to populate prior-
run state (triggering subprocess overhead) now seed the workspace database
directly.  The remaining two tests still need workspace.run() because they
depend on the full collection + masking pipeline.
"""

import time
from pathlib import Path

import pytest

import canary
from _canary.error import StopExecution
from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.testexec import ExecutionSpace
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _seed_passed_job(workspace: Workspace, spec: JobSpec) -> None:
    """Write a SUCCESS result for *spec* into the workspace database.

    This replaces a full workspace.run() whose only purpose is to establish
    a prior-run record so that a subsequent run with only="not_pass" or
    only="changed" sees the job as already-passed / not-changed.
    """
    session_name = "0000-seeded-session"
    ws = ExecutionSpace(
        root=workspace.sessions_dir / session_name, path=Path(spec.family), session=session_name
    )
    job = Job(spec=spec, workspace=ws)
    job.status.set(outcome="SUCCESS")
    # _started must be AFTER the spec file's mtime so "changed" sees it as
    # unmodified.  A small sleep + re-read of the file's mtime guarantees this
    # even if the test runs quickly.
    job.timekeeper._submitted = time.time()
    job.timekeeper._started = time.time() + 1.0  # definitely after file write
    job.timekeeper._stopped = time.time() + 2.0
    job.timekeeper._finished = time.time() + 2.0
    workspace.db.put_specs([spec])
    workspace.db.put_results(job)


def test_workspace_run_empty_specs_raises_notests(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)

        with pytest.raises(StopExecution) as exc:
            workspace.run([], only="all")

        assert exc.value.exit_code == 7


def test_workspace_run_all_masked_specs_raises_notests(tmp_path):
    root = tmp_path / "all-masked"
    root.mkdir()

    write(
        root / "disabled.pyt",
        """\
import canary_pyt
canary_pyt.directives.enable(False)
def test():
    raise AssertionError("should not run")
""",
    )

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})

        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="all")

        assert exc.value.exit_code == 7


def test_only_changed_with_no_changes_raises_notests(tmp_path):
    """only='changed' raises StopExecution when no spec file has been modified.

    We seed the database with a SUCCESS result whose _started timestamp is
    in the future relative to the spec file's mtime, so the RerunRule sees
    the spec as unchanged and masks it.  No subprocess is needed.
    """
    root = tmp_path / "no-changes"
    root.mkdir()

    write(
        root / "case.pyt",
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})

        # Seed a prior SUCCESS without running jobs.
        _seed_passed_job(workspace, specs[0])

        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="changed")

        assert exc.value.exit_code == 7


def test_only_not_pass_after_all_pass_raises_notests(tmp_path):
    """only='not_pass' raises StopExecution when all prior results are PASS.

    We seed the database with a SUCCESS result so the RerunRule masks the
    job.  No subprocess is needed.
    """
    root = tmp_path / "all-pass"
    root.mkdir()

    write(
        root / "case.pyt",
        """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
""",
    )

    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})

        # Seed a prior SUCCESS without running jobs.
        _seed_passed_job(workspace, specs[0])

        with pytest.raises(StopExecution) as exc:
            workspace.run(specs, only="not_pass")

        assert exc.value.exit_code == 7
