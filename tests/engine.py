# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Engine: Workspace.run() split into prepare() and execute()."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import canary
from _canary.core.execspace import ExecutionSpace
from _canary.core.job import Job
from _canary.core.job import JobPhase
from _canary.core.jobspec import JobSpec
from _canary.engine.engine import Engine
from _canary.util.filesystem import working_dir
from _canary.workspace.workspace import Workspace

PASSING = """\
import sys

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
"""

SEEDED = "0000-seeded-session"


def make_workspace(root: Path, *names: str) -> tuple[Workspace, dict[str, JobSpec]]:
    for name in names:
        (root / f"{name}.pyt").write_text(PASSING)
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = Engine(workspace).collect({str(root): []})
    return workspace, {spec.family: spec for spec in specs}


def seed_result(workspace: Workspace, spec: JobSpec, *, outcome: str, submitted: float) -> Job:
    space = ExecutionSpace(
        root=workspace.sessions_dir / SEEDED, path=Path(spec.family), session=SEEDED
    )
    job = Job(spec=spec, workspace=space)
    job.timekeeper.open(at=submitted)
    job.timekeeper.maybe_start(at=submitted + 0.1)
    job.status.set(outcome=outcome)
    job.state.phase = JobPhase.DONE
    workspace.db.put_results(job)
    return job


def test_prepare_does_not_execute_or_persist(tmp_path):
    workspace, specs = make_workspace(tmp_path, "a")
    with working_dir(tmp_path), canary.config.override():
        session = Engine(workspace).prepare(list(specs.values()), only="all")
    assert [job.name for job in session.jobs] == ["a"]
    assert session.reused is False
    assert all(job.workspace.session == session.name for job in session.jobs)
    assert session.lockfile.exists()
    assert not (workspace.refs_dir / "latest").exists()
    assert workspace.db.get_results() == {}


def test_prepare_with_a_masked_job(tmp_path):
    """A job masked by the rerun rule must not reach the Session (which rejects masked jobs)."""
    workspace, specs = make_workspace(tmp_path, "a", "b")
    seed_result(workspace, specs["a"], outcome="SUCCESS", submitted=time.time() - 10)
    with working_dir(tmp_path), canary.config.override():
        session = Engine(workspace).prepare(list(specs.values()), only="not_pass")
    assert [job.name for job in session.jobs] == ["b"]


def test_prepare_inplace_starts_a_new_attempt(tmp_path):
    """In-place reruns keep the old session row; their mid-run rows must be accepted."""
    workspace, specs = make_workspace(tmp_path, "a")
    old = seed_result(workspace, specs["a"], outcome="FAILED", submitted=time.time() - 10)
    old.workspace.dir.mkdir(parents=True)
    with working_dir(tmp_path), canary.config.override():
        session = Engine(workspace).prepare([specs["a"]], inplace=True, only="all")
    (job,) = session.jobs
    assert job.workspace.session == SEEDED
    assert job.timekeeper._submitted == -1.0

    job.on_submit(at=time.time())
    job.on_start(at=time.time())
    workspace.db.put_results(job)
    row = workspace.db.get_results()[job.id]
    assert row["session"] == SEEDED
    assert row["state"].phase is JobPhase.RUNNING


def test_prepare_rewrites_session_dir_variables(tmp_path):
    workspace, specs = make_workspace(tmp_path, "a")
    old = seed_result(workspace, specs["a"], outcome="FAILED", submitted=time.time() - 10)
    old_dir = str(old.workspace.dir)
    original = Job.get_environ_from_spec

    def environ(self):
        env = original(self)
        env["PYTHONPATH"] = old_dir
        env["PATH"] = f"{old_dir}:/usr/bin"
        return env

    Job.get_environ_from_spec = environ  # type: ignore[method-assign]
    try:
        with working_dir(tmp_path), canary.config.override():
            session = Engine(workspace).prepare([specs["a"]], only="all")
    finally:
        Job.get_environ_from_spec = original  # type: ignore[method-assign]
    (job,) = session.jobs
    new_dir = str(job.workspace.dir)
    assert new_dir != old_dir
    assert job.variables["PYTHONPATH"] == new_dir
    assert job.variables["PATH"] == f"{new_dir}:/usr/bin"


def test_execute_prepared_session(tmp_path):
    workspace, specs = make_workspace(tmp_path, "a")
    with working_dir(tmp_path), canary.config.override():
        runner = Engine(workspace)
        session = runner.execute(runner.prepare(list(specs.values()), only="all"))
    assert session.returncode == 0
    latest = (workspace.refs_dir / "latest").read_text()
    assert latest.endswith(session.name)
    row = workspace.db.get_results()[specs["a"].id]
    assert row["session"] == session.name
    assert row["status"].outcome.name == "SUCCESS"
    view = workspace.latest_view()  # the engine registered the live view
    assert view is not None and view.dir.exists()


def test_context_exposes_paths_and_record_spools_then_syncs(tmp_path, monkeypatch):
    workspace, specs = make_workspace(tmp_path, "a")
    calls: list[tuple[str, Job]] = []
    monkeypatch.setattr(workspace.db.queue, "put", lambda job: calls.append(("spool", job)))

    def sync(job: Job) -> None:
        calls.append(("sync", job))
        raise RuntimeError("view failure must not escape record")

    context = Engine(workspace)._context(SimpleNamespace(sync=sync))  # type: ignore[arg-type]
    assert context.root == workspace.root
    assert context.sessions_dir == workspace.sessions_dir
    assert context.cache_dir == workspace.cache_dir
    assert context.reports_dir == workspace.reports_dir

    job = seed_result(workspace, specs["a"], outcome="SUCCESS", submitted=time.time())
    context.record(job)
    assert calls == [("spool", job), ("sync", job)]


FAILING = """\
import sys

def test():
    return 1

if __name__ == "__main__":
    sys.exit(test())
"""

DEPENDENT = """\
import sys
import canary

canary.directives.depends_on("up")

def test():
    pass

if __name__ == "__main__":
    sys.exit(test())
"""


def _dependent_workspace(root: Path, upstream: str) -> tuple[Workspace, dict[str, JobSpec]]:
    (root / "up.pyt").write_text(upstream)
    (root / "down.pyt").write_text(DEPENDENT)
    with working_dir(root), canary.config.override():
        workspace = Workspace.create(root)
        specs = Engine(workspace).collect({str(root): []})
    return workspace, {spec.family: spec for spec in specs}


def test_exec_job_runs_one_job_and_writes_the_database(tmp_path):
    workspace, specs = make_workspace(tmp_path, "a")
    events: list[str] = []
    with working_dir(tmp_path), canary.config.override():
        engine = Engine(workspace)
        job = engine.exec_job(engine.job_for("a"), observer=lambda e: events.append(e["event"]))
    assert job.status.outcome.name == "SUCCESS"
    assert events[:3] == ["job_submitted", "job_staged", "job_started"]
    assert workspace.db.get_results()[specs["a"].id]["session"] == job.workspace.session


def test_exec_job_in_a_nested_process_spools_instead(tmp_path, monkeypatch):
    workspace, _ = make_workspace(tmp_path, "a")
    spooled: list[Job] = []
    monkeypatch.setattr(workspace, "canary_level", 1)
    monkeypatch.setattr(workspace.db.queue, "put", spooled.append)
    monkeypatch.setattr(workspace.db, "put_results", lambda *jobs: pytest.fail("wrote SQLite"))
    with working_dir(tmp_path), canary.config.override():
        engine = Engine(workspace)
        job = engine.exec_job(engine.job_for("a", session="nested"))
    assert spooled == [job]
    assert job.workspace.session == "nested"


def test_exec_job_records_a_job_blocked_by_a_failed_upstream(tmp_path):
    workspace, specs = _dependent_workspace(tmp_path, FAILING)
    with working_dir(tmp_path), canary.config.override():
        engine = Engine(workspace)
        engine.exec_job(engine.job_for("up"))
        job = engine.exec_job(engine.job_for("down"))
    assert job.status.outcome.name == "BLOCKED"
    assert workspace.db.get_results()[specs["down"].id]["status"].outcome.name == "BLOCKED"


def test_exec_job_refuses_a_job_whose_upstream_has_not_run(tmp_path):
    workspace, _ = _dependent_workspace(tmp_path, PASSING)
    with working_dir(tmp_path), canary.config.override():
        engine = Engine(workspace)
        with pytest.raises(RuntimeError, match="not ready"):
            engine.exec_job(engine.job_for("down"))
