# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from typing import cast

import canary_flux.executor as ex


class FakeTimekeeper:
    def __init__(self):
        self.submitted = -1.0
        self.started = -1.0
        self.finished = -1.0

    def duration(self):
        if self.started > 0 and self.finished > 0:
            return self.finished - self.started
        return -1.0


class FakeState:
    def __init__(self):
        self.done = False
        self.running = False

    def is_done(self):
        return self.done

    def is_running(self):
        return self.running


class FakeStatus:
    def __init__(self):
        self.outcome = "NONE"
        self.reason = None
        self.code = -1
        self.unset = True
        self.success = False
        self.failure = False
        self.skipped = False

    def is_unset(self):
        return self.unset

    def is_success(self):
        return self.success

    def is_failure(self):
        return self.failure

    def is_skipped(self):
        return self.skipped

    def display_name(self, style="none"):
        return self.outcome

    def set(self, outcome=None, reason=None, code=-1, category=None):
        self.outcome = outcome or self.outcome
        self.reason = reason
        self.code = code
        self.unset = False
        if self.outcome in ("ERROR", "FAILED", "BROKEN"):
            self.failure = True


class FakeWorkspace:
    def __init__(self, root):
        self.root = Path(root)
        self.dir = self.root / "job"
        self.session = "s"

    def joinpath(self, *parts):
        return self.dir.joinpath(*parts)


class FakeJob:
    def __init__(self, id, *, ready=True, deps=None, workspace_root=None):
        self.id = id
        self.name = id
        self._ready = ready
        self._runnable = True
        self.dependencies = deps or []
        self.timekeeper = FakeTimekeeper()
        self.state = FakeState()
        self.status = FakeStatus()
        self.workspace = FakeWorkspace(workspace_root or Path.cwd())
        self.cpus = 1
        self.gpus = 0
        self.nodes = 1
        self.measurements = {}
        self.saved = False
        self.refreshed = False

    def refresh_readiness(self):
        # Test hook may override _ready/_runnable externally.
        pass

    def is_ready(self):
        return self._ready

    def is_runnable(self):
        return self._runnable and not self.state.is_done()

    def cost(self):
        return 1.0

    def total_timeout(self):
        return 10.0

    def display_name(self, *args, **kwargs):
        return self.name

    def on_submitted(self):
        pass

    def on_started(self):
        self.state.running = True

    def on_finished(self):
        self.state.done = True
        self.state.running = False

    def set_status(self, outcome=None, reason=None, code=-1, category=None):
        self.status.set(outcome=outcome, reason=reason, code=code, category=category)

    def save(self):
        self.saved = True

    def refresh(self):
        self.refreshed = True

    def add_measurement(self, name, value):
        self.measurements[name] = value


def test_execution_slot_queued_live_until_started():
    job = FakeJob("j1")

    slot = ex.ExecutionSlot(job=cast(Any, job), qrank=1, qsize=1, worker_id=1)

    assert slot.phase_time("Running") == -1.0
    assert slot.total_time(("Running",)) == -1.0
    assert slot.phase_time("Queued") >= 0.0


def test_execution_slot_running_after_started():
    job = FakeJob("j1")

    slot = ex.ExecutionSlot(job=cast(Any, job), qrank=1, qsize=1, worker_id=1)

    slot.timer.start("Queued", at=100.0)
    slot.on_started(110.0)
    slot.on_finished(115.5)

    assert slot.phase_time("Queued", live=False) == 10.0
    assert slot.phase_time("Running", live=False) == 5.5
    assert slot.total_time(("Queued", "Running"), live=False) == 15.5


def test_reporter_queue_tracks_states():
    jobs = [FakeJob("a"), FakeJob("b")]
    q = ex.FluxReporterQueue(cast(Any, jobs))

    assert [j.id for j in q.pending()] == ["a", "b"]
    assert len(q.jobs()) == 2

    q.mark_submitted(cast(Any, jobs[0]))
    assert [j.id for j in q.pending()] == ["b"]

    q.mark_started(cast(Any, jobs[0]))
    assert [j.id for j in q.pending()] == ["b"]

    q.mark_finished(cast(Any, jobs[0]))
    assert [j.id for j in q.pending()] == ["b"]

    text = q.status(start=time.time())
    assert "RUNNING" in text or "PENDING" in text or "COMPLETE" in text


class FakeConfig:
    def __init__(self):
        self.values = {
            "flux_max_submitted": 0,
            "flux_backend": "flux",
            "flux_time_limit": 100,
            "flux_submit_args": None,
        }

    def getoption(self, name, default=None):
        return self.values.get(name, default)

    def get(self, name, default=None):
        return default


class FakeRunnerWorkspace:
    def __init__(self, tmp_path):
        self.cache_dir = tmp_path / "cache"
        self.root = tmp_path / ".canary"

        self.db = SimpleNamespace(queue=SimpleNamespace(put=lambda job: None))


class FakeRunner:
    def __init__(self, jobs, tmp_path):
        self.jobs = jobs
        self.session = "session1"
        self.workspace = FakeRunnerWorkspace(tmp_path)


def test_ready_jobs_only_returns_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(ex.canary, "config", FakeConfig())

    ready = FakeJob("ready", ready=True)
    not_ready = FakeJob("not-ready", ready=False)

    runner = FakeRunner([ready, not_ready], tmp_path)
    xtor = ex.FluxDirectExecutor(runner)

    result = xtor._ready_jobs()

    assert [job.id for job in result] == ["ready"]


def test_submit_ready_jobs_only_submits_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(ex.canary, "config", FakeConfig())

    ready = FakeJob("ready", ready=True)
    not_ready = FakeJob("not-ready", ready=False)

    runner = FakeRunner([ready, not_ready], tmp_path)
    xtor = ex.FluxDirectExecutor(runner)

    submitted = []

    class FakeFuture:
        jobid = "flux123"

        def add_jobstart_callback(self, fn):
            pass

        def add_jobid_callback(self, fn):
            pass

    class FakeSubmitter:
        def submit(self, spec, exclusive=False):
            submitted.append((spec, exclusive))
            return FakeFuture()

    monkeypatch.setattr(xtor, "_hpc_jobspec", lambda job: SimpleNamespace(name=job.id))

    made_progress = xtor._submit_ready_jobs(FakeSubmitter())

    assert made_progress is True
    assert len(submitted) == 1
    assert submitted[0][0].name == "ready"
    assert submitted[0][1] is False
    assert "ready" not in xtor.pending
    assert "not-ready" in xtor.pending


def test_finalize_blocked_jobs_queues_parent_side(monkeypatch, tmp_path):
    monkeypatch.setattr(ex.canary, "config", FakeConfig())

    blocked = FakeJob("blocked", ready=False)
    blocked.state.done = True
    blocked.status.set(outcome="BLOCKED", reason="dependency failed")

    queued = []

    runner = FakeRunner([blocked], tmp_path)
    runner.workspace.db.queue.put = lambda job: queued.append(job)

    xtor = ex.FluxDirectExecutor(runner)

    made_progress = xtor._finalize_blocked_jobs()

    assert made_progress is True
    assert "blocked" not in xtor.pending
    assert "blocked" in xtor.finished
    assert queued == [blocked]


def test_mark_finished_uses_job_timing_for_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(ex.canary, "config", FakeConfig())

    job = FakeJob("j1")
    runner = FakeRunner([job], tmp_path)
    xtor = ex.FluxDirectExecutor(runner)

    # Avoid filesystem/proc-info side effects in this unit test.
    monkeypatch.setattr(xtor, "_write_proc_info", lambda job, proc_info: None)

    # Parent observes future completion at 110.
    monkeypatch.setattr(ex.time, "time", lambda: 110.0)

    slot = ex.ExecutionSlot(job=cast(Any, job), qrank=1, qsize=1, worker_id=1)

    # Simulate Flux lifecycle before _mark_finished:
    # submitted at 100, Flux started at 101.
    slot.timer.start("Queued", at=100.0)
    slot.timer.transition("Startup", at=101.0)

    xtor.slots_by_id[job.id] = slot
    xtor.running[job.id] = slot

    # Child testcase.lock timing.
    job.timekeeper.submitted = 100.0
    job.timekeeper.started = 102.0
    job.timekeeper.finished = 107.0
    job.status.set(outcome="SUCCESS", code=0)

    xtor._mark_finished(job.id, rc=0, exc=None, proc_info={"jobid": "flux1"})

    assert job.id in xtor.finished

    assert slot.phase_time("Queued", live=False) == 1.0
    assert slot.phase_time("Startup", live=False) == 1.0
    assert slot.phase_time("Running", live=False) == 5.0
    assert slot.phase_time("Teardown", live=False) == 3.0
    assert slot.total_time(("Queued", "Startup", "Running", "Teardown"), live=False) == 10.0

    assert job.measurements["flux"] == {"jobid": "flux1"}

    timing = job.measurements["flux_timing"]
    assert timing["queue_time"] == 1.0
    assert timing["startup_time"] == 1.0
    assert timing["execution_time"] == 5.0
    assert timing["teardown_time"] == 3.0
    assert timing["elapsed_time"] == 10.0
