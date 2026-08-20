# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from typing import cast

import canary_flux.executor as ex
from _canary.job import JobPhase
from _canary.job import JobState
from _canary.status import Status
from _canary.timekeeper import Timekeeper


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
        self.timekeeper = Timekeeper()
        self.state = JobState()
        self.status = Status()
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

    def is_done(self):
        return self.state.is_done()

    def cost(self):
        return 1.0

    def total_timeout(self):
        return 10.0

    def display_name(self, *args, **kwargs):
        return self.name

    def on_submit(self, at=None):
        self.timekeeper.maybe_open(at=at)
        self.state.phase = JobPhase.PENDING

    def on_stage(self, at=None):
        self.timekeeper.maybe_stage(at=at)
        self.state.phase = JobPhase.STAGING

    def on_start(self, at=None):
        self.timekeeper.maybe_start(at=at)
        self.state.phase = JobPhase.RUNNING

    def on_stop(self, at=None):
        self.timekeeper.maybe_stop(at=at)
        self.state.phase = JobPhase.FINISHING

    def on_finish(self, at=None):
        self.timekeeper.maybe_close(at=at)
        self.state.phase = JobPhase.DONE

    def set_status(self, outcome=None, reason=None, code=-1, category=None):
        self.status.set(outcome=outcome, reason=reason, code=code, category=category)

    def save(self):
        self.saved = True

    def refresh(self):
        self.refreshed = True

    def add_measurement(self, name, value):
        self.measurements[name] = value


def test_flux_job_timekeeper_unstarted_phases():
    job = FakeJob("j1")
    flux_job = ex.FluxJob(
        inner=cast(Any, job), allocation_requested_at=100.0, allocation_granted_at=105.0
    )

    slot = ex.ExecutionSlot(job=cast(Any, flux_job), qrank=1, qsize=1, worker_id=1)

    slot.on_submit(at=100.0)
    slot.on_stage(at=105.0)

    assert flux_job.timekeeper.pending(live=False) == 5.0
    assert flux_job.timekeeper.staging(live=False) == -1.0
    assert flux_job.timekeeper.running(live=False) == -1.0
    assert flux_job.timekeeper.finishing(live=False) == -1.0
    assert flux_job.timekeeper.total(live=False) == -1.0


def test_flux_job_timekeeper_full_lifecycle():
    job = FakeJob("j1")
    flux_job = ex.FluxJob(
        inner=cast(Any, job), allocation_requested_at=99.0, allocation_granted_at=100.0
    )

    slot = ex.ExecutionSlot(job=cast(Any, flux_job), qrank=1, qsize=1, worker_id=1)

    # Recommended FluxJob lifecycle:
    #   open   = allocation requested
    #   stage  = individual JobSpecV1 submitted
    #   start  = Flux job-start callback
    #   stop   = inner Canary job finished
    #   finish = parent observed Flux future result
    slot.on_submit(at=99.0)
    slot.on_stage(at=100.0)
    slot.on_start(at=101.0)
    slot.on_stop(at=107.0)
    slot.on_finish(at=110.0)

    assert flux_job.timekeeper.pending(live=False) == 1.0
    assert flux_job.timekeeper.staging(live=False) == 1.0
    assert flux_job.timekeeper.running(live=False) == 6.0
    assert flux_job.timekeeper.finishing(live=False) == 3.0
    assert flux_job.timekeeper.total(live=False) == 11.0


def test_reporter_queue_tracks_states():
    jobs = [FakeJob("a"), FakeJob("b")]
    flux_jobs = [ex.FluxJob(inner=cast(Any, job)) for job in jobs]
    q = ex.FluxReporterQueue(flux_jobs)

    assert [j.id for j in q.pending()] == ["a", "b"]
    assert len(q.jobs()) == 2

    q.mark_submitted(flux_jobs[0])
    assert [j.id for j in q.pending()] == ["b"]

    q.mark_started(flux_jobs[0])
    assert [j.id for j in q.pending()] == ["b"]

    q.mark_finished(flux_jobs[0])
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
    xtor = ex.FluxDirectExecutor(cast(Any, runner))

    result = xtor._ready_jobs()

    assert [job.id for job in result] == ["ready"]


def test_submit_ready_jobs_only_submits_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(ex.canary, "config", FakeConfig())

    ready = FakeJob("ready", ready=True)
    not_ready = FakeJob("not-ready", ready=False)

    runner = FakeRunner([ready, not_ready], tmp_path)
    xtor = ex.FluxDirectExecutor(cast(Any, runner))

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
    blocked.state.phase = JobPhase.DONE
    blocked.status.set(outcome="BLOCKED", reason="dependency failed")

    queued = []

    runner = FakeRunner([blocked], tmp_path)
    runner.workspace.db.queue.put = lambda job: queued.append(job)

    xtor = ex.FluxDirectExecutor(cast(Any, runner))

    made_progress = xtor._finalize_blocked_jobs()

    assert made_progress is True
    assert "blocked" not in xtor.pending
    assert "blocked" in xtor.finished
    assert queued == [blocked]


def test_mark_finished_records_flux_timing_and_overhead(monkeypatch, tmp_path):
    monkeypatch.setattr(ex.canary, "config", FakeConfig())

    job = FakeJob("j1")
    runner = FakeRunner([job], tmp_path)
    xtor = ex.FluxDirectExecutor(
        cast(Any, runner), allocation_requested_at=98.0, allocation_granted_at=99.0
    )

    # Avoid filesystem/proc-info side effects in this unit test.
    monkeypatch.setattr(xtor, "_write_proc_info", lambda job, proc_info: None)

    # Parent observes future completion at 110.
    monkeypatch.setattr(ex.time, "time", lambda: 110.0)

    flux_job = xtor.flux_jobs[job.id]
    slot = ex.ExecutionSlot(job=cast(Any, flux_job), qrank=1, qsize=1, worker_id=1)

    # Simulate Flux lifecycle before _mark_finished:
    # allocation requested at 98, JobSpec submitted at 100, Flux started at 101.
    slot.on_submit(at=98.0)
    slot.on_stage(at=100.0)
    slot.on_start(at=101.0)

    xtor.slots_by_id[job.id] = slot
    xtor.running[job.id] = slot

    # Child testcase.lock timing.
    job.timekeeper.open(at=102.0)
    job.timekeeper.stage(at=102.5)
    job.timekeeper.start(at=103.0)
    job.timekeeper.stop(at=106.0)
    job.timekeeper.close(at=107.0)
    job.status.set(outcome="SUCCESS", code=0)

    xtor._mark_finished(job.id, rc=0, exc=None, proc_info={"jobid": "flux1"})

    assert job.id in xtor.finished

    assert flux_job.timekeeper.pending(live=False) == 2.0
    assert flux_job.timekeeper.staging(live=False) == 1.0
    assert flux_job.timekeeper.running(live=False) == 6.0
    assert flux_job.timekeeper.finishing(live=False) == 3.0
    assert flux_job.timekeeper.total(live=False) == 12.0

    flux = job.measurements["flux"]

    assert flux["proc_info"] == {"jobid": "flux1"}

    timing = flux["timing"]
    assert timing["allocation"]["requested_at"] == 98.0
    assert timing["allocation"]["granted_at"] == 99.0
    assert timing["allocation"]["wait_seconds"] == 1.0

    jobspec = timing["jobspec_v1"]
    assert jobspec["submitted_at"] == 100.0
    assert jobspec["flux_started_at"] == 101.0
    assert jobspec["inner_opened_at"] == 102.0
    assert jobspec["inner_started_at"] == 103.0
    assert jobspec["inner_stopped_at"] == 106.0
    assert jobspec["inner_finished_at"] == 107.0
    assert jobspec["flux_finished_at"] == 110.0

    durations = timing["durations"]
    assert durations["allocation_request_to_jobspec_submit_seconds"] == 2.0
    assert durations["jobspec_submit_to_flux_start_seconds"] == 1.0
    assert durations["flux_start_to_inner_finish_seconds"] == 6.0
    assert durations["inner_finish_to_flux_return_seconds"] == 3.0
    assert durations["flux_jobspec_total_seconds"] == 12.0
    assert durations["allocation_wait_seconds"] == 1.0
    assert durations["allocation_granted_to_jobspec_submit_seconds"] == 1.0
    assert durations["flux_start_to_inner_open_seconds"] == 1.0
    assert durations["flux_start_to_inner_start_seconds"] == 2.0
    assert durations["inner_total_seconds"] == 5.0
    assert durations["inner_pending_seconds"] == 0.5
    assert durations["inner_staging_seconds"] == 0.5
    assert durations["inner_command_seconds"] == 3.0
    assert durations["inner_finishing_seconds"] == 1.0
    assert durations["inner_stop_to_flux_return_seconds"] == 4.0

    overhead = flux["overhead"]
    assert overhead["launch_seconds"] == 1.0
    assert overhead["return_seconds"] == 3.0
    assert overhead["return_after_inner_stop_seconds"] == 4.0
    assert overhead["total_external_seconds"] == 4.0
