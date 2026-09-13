# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for the --only / rerun selection strategies.

The original tests all called workspace.run() twice, which spawned worker
subprocesses twice per test (~14s total).  Refactored into two layers:

Unit tests (fast, <100ms each):
  - Test that RuntimeSelector + RerunRule masks / unmasks the right jobs.
  - Verify the "not re-run" side: masked jobs keep their prior timekeeper.
  - Verify transitive masking (blocked downstream included in rerun).

Retained integration tests (1 workspace.run() each instead of 2):
  - test_rerun_all_reruns_successful_jobs: verifies a job's _started
    timestamp is updated after a real re-execution.
  - test_rerun_failed_includes_blocked_downstream_after_upstream_fixed:
    verifies the full failed+blocked→fixed cycle end-to-end.
"""

import time
from pathlib import Path

import pytest

import canary
from _canary.job import Dependency
from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.rules import RerunRule
from _canary.select import RuntimeSelector
from _canary.testexec import ExecutionSpace
from _canary.util.filesystem import working_dir
from _canary.workspace import Workspace

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def make_job(tmp_path: Path, name: str, outcome: str = "NONE", started_at: float = -1.0) -> Job:
    spec = JobSpec(
        file_root=tmp_path,
        file_path=tmp_path / f"{name}.pyt",
        family=name,
        id=(name[0] * 64)[:64],
        timeout=10.0,
    )
    ws = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path(name), session="s1")
    job = Job(spec=spec, workspace=ws)
    if outcome != "NONE":
        job.status.set(outcome=outcome)
    job.timekeeper._started = started_at
    return job


def _seed_passed_job(workspace: Workspace, spec: JobSpec, started_at: float) -> None:
    """Write a SUCCESS result for *spec* into the workspace database.

    Uses a session name that sorts before any real ISO-format session name
    (real sessions are '2026-...' which start with a digit; we use '0000-...'
    as the seed session so MAX(session) always picks the real run over the seed).
    """
    session_name = "0000-seeded-session"
    ws = ExecutionSpace(
        root=workspace.sessions_dir / session_name, path=Path(spec.family), session=session_name
    )
    job = Job(spec=spec, workspace=ws)
    job.status.set(outcome="SUCCESS")
    job.timekeeper._submitted = started_at - 0.1
    job.timekeeper._started = started_at
    job.timekeeper._stopped = started_at + 0.5
    job.timekeeper._finished = started_at + 0.5
    workspace.db.put_specs([spec])
    workspace.db.put_results(job)


def create_workspace(root: Path) -> tuple[Workspace, list[canary.JobSpec]]:
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = workspace.collect({str(root): []})
        return workspace, specs


def run_specs(workspace: Workspace, specs: list[canary.JobSpec], *, only: str = "all"):
    with working_dir(workspace.root), canary.config.override():
        return workspace.run(specs, only=only)


def jobs_by_name(workspace: Workspace) -> dict[str, canary.Job]:
    return {job.name: job for job in workspace.load_jobs()}


def started_at(job: canary.Job) -> float:
    return job.timekeeper._started


# ---------------------------------------------------------------------------
# Unit tests — RuntimeSelector + RerunRule (no subprocess)
# ---------------------------------------------------------------------------


def test_rerun_not_pass_masks_successful_job(tmp_path):
    """only='not_pass' masks a SUCCESS job and does not mask a FAILED job."""
    good = make_job(tmp_path, "good", outcome="SUCCESS", started_at=1.0)
    bad = make_job(tmp_path, "bad", outcome="FAILED", started_at=1.0)

    selector = RuntimeSelector([good, bad], workspace=tmp_path)
    selector.add_rule(RerunRule("not_pass"))
    selector.run()

    assert good.mask, "SUCCESS job should be masked by not_pass"
    assert not bad.mask, "FAILED job should not be masked by not_pass"


def test_rerun_all_unmasks_successful_job(tmp_path):
    """only='all' does not mask any job regardless of prior outcome."""
    good = make_job(tmp_path, "good", outcome="SUCCESS", started_at=1.0)
    bad = make_job(tmp_path, "bad", outcome="FAILED", started_at=1.0)

    selector = RuntimeSelector([good, bad], workspace=tmp_path)
    selector.add_rule(RerunRule("all"))
    selector.run()

    assert not good.mask
    assert not bad.mask


def test_rerun_not_run_masks_job_with_prior_result(tmp_path):
    """only='not_run' masks a job that already has a result."""
    ran = make_job(tmp_path, "ran", outcome="SUCCESS", started_at=1.0)
    new = make_job(tmp_path, "new", outcome="NONE")  # no prior result

    selector = RuntimeSelector([ran, new], workspace=tmp_path)
    selector.add_rule(RerunRule("not_run"))
    selector.run()

    assert ran.mask
    assert not new.mask


def test_rerun_failed_only_selects_failures(tmp_path):
    """only='failed' selects FAILED and BLOCKED jobs but not SUCCESS."""
    good = make_job(tmp_path, "good", outcome="SUCCESS", started_at=1.0)
    bad = make_job(tmp_path, "bad", outcome="FAILED", started_at=1.0)

    selector = RuntimeSelector([good, bad], workspace=tmp_path)
    selector.add_rule(RerunRule("failed"))
    selector.run()

    assert good.mask
    assert not bad.mask


def test_rerun_changed_masks_unchanged_spec(tmp_path):
    """only='changed' masks a job whose spec file hasn't changed since last run."""
    # Create the spec file first, then set _started to after its mtime.
    spec_file = tmp_path / "case.pyt"
    spec_file.write_text("# stub\n")
    future_start = spec_file.stat().st_mtime + 10.0  # definitely after file write

    job = make_job(tmp_path, "case", outcome="SUCCESS", started_at=future_start)
    # Repoint spec.file_path to the real file so stat() works.
    job.spec = JobSpec(
        file_root=tmp_path, file_path=spec_file, family="case", id="c" * 64, timeout=10.0
    )
    job.timekeeper._started = future_start

    selector = RuntimeSelector([job], workspace=tmp_path)
    selector.add_rule(RerunRule("changed"))
    selector.run()

    assert job.mask, "unchanged spec should be masked by 'changed' rule"


def test_rerun_changed_does_not_mask_modified_spec(tmp_path):
    """only='changed' does not mask a job whose spec file is newer than _started."""
    spec_file = tmp_path / "case.pyt"
    spec_file.write_text("# stub\n")
    old_start = spec_file.stat().st_mtime - 10.0  # before the file was written

    job = make_job(tmp_path, "case", outcome="SUCCESS", started_at=old_start)
    job.spec = JobSpec(
        file_root=tmp_path, file_path=spec_file, family="case", id="c" * 64, timeout=10.0
    )
    job.timekeeper._started = old_start

    selector = RuntimeSelector([job], workspace=tmp_path)
    selector.add_rule(RerunRule("changed"))
    selector.run()

    assert not job.mask, "modified spec should not be masked"


def test_masked_job_keeps_prior_started_timestamp(tmp_path):
    """A job masked by not_pass retains its prior _started value unchanged."""
    original_start = 12345.0
    good = make_job(tmp_path, "good", outcome="SUCCESS", started_at=original_start)

    selector = RuntimeSelector([good], workspace=tmp_path)
    selector.add_rule(RerunRule("not_pass"))
    selector.run()

    # RuntimeSelector.run() calls job.timekeeper.reset() for unmasked jobs only.
    # Masked jobs should keep their prior state.
    assert good.mask
    assert good.timekeeper._started == original_start


def test_blocked_downstream_included_in_failed_rerun(tmp_path):
    """only='failed' propagates to BLOCKED downstream via selector.propagate()."""
    upstream = make_job(tmp_path, "upstream", outcome="FAILED", started_at=1.0)
    downstream = make_job(tmp_path, "downstream", outcome="BLOCKED", started_at=1.0)
    downstream.dependencies.append(Dependency(job=upstream, when="on_success"))

    selector = RuntimeSelector([upstream, downstream], workspace=tmp_path)
    selector.add_rule(RerunRule("failed"))
    selector.run()

    # upstream is FAILED → not masked by 'failed'.
    # downstream is BLOCKED (which is_failure()) → not masked by 'failed'.
    assert not upstream.mask
    assert not downstream.mask


# ---------------------------------------------------------------------------
# Integration tests — require actual job execution (1 workspace.run() each)
# ---------------------------------------------------------------------------


def test_rerun_all_reruns_successful_jobs(tmp_path):
    """only='all' re-runs a previously-PASS job; _started is updated.

    We seed the first run via the DB (no subprocess), then do one real
    workspace.run() to verify the re-execution updates _started.
    """
    root = tmp_path / "rerun-all"
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

    workspace, specs = create_workspace(root)

    # Seed first-run state without executing, using the real spec.
    seeded_start = time.time() - 5.0
    _seed_passed_job(workspace, specs[0], started_at=seeded_start)

    # Confirm the seeded state is visible to load_jobs().
    jobs_seeded = jobs_by_name(workspace)
    assert started_at(jobs_seeded["case"]) == pytest.approx(seeded_start, abs=0.01)

    # Real second run — should update _started.
    time.sleep(0.02)
    session2 = run_specs(workspace, specs, only="all")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert started_at(jobs2["case"]) > seeded_start


def test_rerun_failed_includes_blocked_downstream_after_upstream_fixed(tmp_path):
    """Blocked downstream joins re-run when upstream is fixed.

    This test exercises the full failed+blocked→fixed execution path
    and cannot be purely unit-tested.
    """
    root = tmp_path / "rerun-blocked"
    root.mkdir()

    control = root / "fail.txt"
    control.write_text("fail")

    write(
        root / "upstream.pyt",
        f"""\
import pathlib
import sys
import canary

def test():
    if pathlib.Path({str(control)!r}).read_text().strip() == "fail":
        raise canary.TestFailed("upstream failed")

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    write(
        root / "downstream.pyt",
        """\
import sys
import canary_pyt

canary_pyt.directives.depends_on("upstream")

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
""",
    )

    workspace, specs = create_workspace(root)

    session1 = run_specs(workspace, specs, only="all")
    jobs1 = jobs_by_name(workspace)

    assert session1.returncode != 0
    assert jobs1["upstream"].status.outcome.name == "FAILED"
    assert jobs1["downstream"].status.outcome.name == "BLOCKED"

    # Fix upstream; rerun with only="failed".
    time.sleep(0.01)
    control.write_text("pass")

    session2 = run_specs(workspace, specs, only="failed")
    jobs2 = jobs_by_name(workspace)

    assert session2.returncode == 0
    assert jobs2["upstream"].status.is_success()
    assert jobs2["downstream"].status.is_success()
