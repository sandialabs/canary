# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

import canary
from _canary.job import Job
from _canary.jobspec import JobSpec
from _canary.testexec import ExecutionSpace
from _canary.workspace import Workspace


def make_job(tmp_path: Path, name: str = "case") -> Job:
    spec = JobSpec(
        file_root=tmp_path,
        file_path=Path(f"{name}.pyt"),
        family=name,
        id=(name[0] * 64)[:64],
        timeout=10.0,
    )
    workspace = ExecutionSpace(root=tmp_path / "sessions" / "s1", path=Path(name), session="s1")
    return Job(spec=spec, workspace=workspace)


def test_job_save_refresh_roundtrip_preserves_status_timekeeper_measurements(tmp_path):
    job = make_job(tmp_path)

    job.status.set(outcome="SUCCESS")
    job.timekeeper.submitted = 1.0
    job.timekeeper.started = 2.0
    job.timekeeper.finished = 5.0
    job.measurements.add_measurement("answer", 42)
    job.save()

    job.status.reset()
    job.timekeeper.reset()
    job.measurements.data.clear()

    job.refresh()

    assert job.status.is_success()
    assert job.timekeeper.submitted == 1.0
    assert job.timekeeper.started == 2.0
    assert job.timekeeper.finished == 5.0
    assert job.measurements.data["answer"] == 42


def test_job_refresh_missing_lock_is_noop(tmp_path):
    job = make_job(tmp_path)

    job.status.set(outcome="FAILED", reason="before")
    job.timekeeper.submitted = 1.0
    job.timekeeper.started = 2.0
    job.timekeeper.finished = 3.0

    job.refresh()

    assert job.status.outcome.name == "FAILED"
    assert job.status.reason == "before"
    assert job.timekeeper.submitted == 1.0
    assert job.timekeeper.started == 2.0
    assert job.timekeeper.finished == 3.0


def test_job_refresh_corrupt_lock_is_noop(tmp_path):
    job = make_job(tmp_path)
    job.workspace.create(exist_ok=True)
    job.lockfile.write_text("{not valid json")

    job.status.set(outcome="FAILED", reason="before")
    job.timekeeper.submitted = 1.0
    job.timekeeper.started = 2.0
    job.timekeeper.finished = 3.0

    job.refresh()

    assert job.status.outcome.name == "FAILED"
    assert job.status.reason == "before"
    assert job.timekeeper.submitted == 1.0
    assert job.timekeeper.started == 2.0
    assert job.timekeeper.finished == 3.0


def test_workspace_db_put_result_from_saved_job(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()

    with canary.config.override():
        workspace = Workspace.create(root)

    job = make_job(root)
    job.status.set(outcome="SUCCESS")
    job.timekeeper.submitted = 1.0
    job.timekeeper.started = 2.0
    job.timekeeper.finished = 3.0
    job.save()

    workspace.db.put_results(job)

    results = workspace.db.get_results(ids=[job.id])
    assert job.id in results
    assert results[job.id]["status"].is_success()
