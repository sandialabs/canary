# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for session-end reconciliation of unfinished jobs."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from _canary.job import BaseJob
from _canary.job import JobPhase
from _canary.job import JobState
from _canary.runtest import Runner
from _canary.runtest import _record_finish_failure
from _canary.runtest import reconcile_unfinished_jobs
from _canary.status import Status
from _canary.timekeeper import Timekeeper


class DummyJob(BaseJob):
    def __init__(self, id: str = "a" * 64, name: str = "job") -> None:
        self._id = id
        self.name = name
        self.state = JobState()
        self.timekeeper = Timekeeper()
        self._status = Status()
        self.measurements = {}
        self.saved = False

    @property
    def id(self) -> str:
        return self._id

    @property
    def status(self) -> Status:
        return self._status

    def cost(self) -> float:
        return 1.0

    def required_resources(self):
        return []

    def assign_resources(self, arg):
        pass

    def free_resources(self):
        return {}

    def refresh_readiness(self) -> None:
        pass

    def is_runnable(self) -> bool:
        return True

    def is_ready(self) -> bool:
        return True

    def total_timeout(self) -> float:
        return 1.0

    def refresh(self) -> None:
        pass

    def save(self) -> None:
        self.saved = True

    def display_name(self, **kwargs: Any) -> str:
        return self.name


def _runner(jobs: list[DummyJob]) -> Runner:
    return Runner(jobs=jobs, session="s", workspace=SimpleNamespace())  # type: ignore[arg-type]


def test_reconcile_marks_pending_job_cancelled():
    job = DummyJob()  # phase PENDING, status unset, never started
    n = reconcile_unfinished_jobs(_runner([job]), interrupted=False)
    assert n == 1
    assert job.state.is_done()
    assert job.status.outcome.name == "CANCELLED"
    assert job.status.category.value == "ABORTED"
    assert job.saved


def test_reconcile_marks_pending_job_interrupted_when_interrupted():
    job = DummyJob()
    n = reconcile_unfinished_jobs(_runner([job]), interrupted=True)
    assert n == 1
    assert job.state.is_done()
    assert job.status.outcome.name == "INTERRUPTED"
    assert "Keyboard interrupt" in (job.status.reason or "")


def test_reconcile_interrupt_marks_running_job_interrupted_not_broken():
    """On Ctrl-C an in-flight job is INTERRUPTED, not BROKEN."""
    job = DummyJob()
    job.state.phase = JobPhase.RUNNING
    job.timekeeper.start()  # genuinely started
    n = reconcile_unfinished_jobs(_runner([job]), interrupted=True)
    assert n == 1
    assert job.state.is_done()
    assert job.status.outcome.name == "INTERRUPTED"
    assert job.status.category.value == "ABORTED"


def test_reconcile_noninterrupt_started_job_broken():
    """Without an interrupt, a job that genuinely started but never reported is BROKEN."""
    job = DummyJob()
    job.timekeeper.start()  # _started > 0
    n = reconcile_unfinished_jobs(_runner([job]), interrupted=False)
    assert n == 1
    assert job.state.is_done()
    assert job.status.outcome.name == "BROKEN"
    assert job.status.category.value == "FAIL"


def test_reconcile_noninterrupt_never_started_cancelled():
    """A RUNNING phase without a real start timestamp is treated as never-started."""
    job = DummyJob()
    job.state.phase = JobPhase.RUNNING  # optimistically marked (e.g. HPC), never started
    n = reconcile_unfinished_jobs(_runner([job]), interrupted=False)
    assert n == 1
    assert job.status.outcome.name == "CANCELLED"


def test_reconcile_leaves_terminal_jobs_untouched():
    done = DummyJob()
    done.state.phase = JobPhase.DONE
    done.status.set(category="PASS", outcome="SUCCESS")
    n = reconcile_unfinished_jobs(_runner([done]), interrupted=True)
    assert n == 0
    assert done.status.outcome.name == "SUCCESS"
    assert not done.saved


def test_reconcile_mixed_batch_on_interrupt():
    done = DummyJob(id="d" * 64)
    done.state.phase = JobPhase.DONE
    done.status.set(category="FAIL", outcome="FAILED")
    pending = DummyJob(id="p" * 64)
    running = DummyJob(id="r" * 64)
    running.state.phase = JobPhase.RUNNING
    running.timekeeper.start()

    n = reconcile_unfinished_jobs(_runner([done, pending, running]), interrupted=True)
    assert n == 2
    assert done.status.outcome.name == "FAILED"
    # On interrupt both unfinished jobs are INTERRUPTED regardless of phase.
    assert pending.status.outcome.name == "INTERRUPTED"
    assert running.status.outcome.name == "INTERRUPTED"
    assert all(j.state.is_done() for j in (done, pending, running))


def test_record_finish_failure_preserves_status_and_writes_output(tmp_path):
    """A failing finish hook is recorded to the job output, not the job status."""

    written: list[str] = []

    @contextmanager
    def openfile(name, mode="r"):
        assert mode == "a"
        f = tmp_path / name
        with open(f, mode, encoding="utf-8") as fh:
            yield fh
        written.append(f.read_text(encoding="utf-8"))

    job = DummyJob()
    job.status.set(category="PASS", outcome="SUCCESS")
    job.stdout = "canary-out.txt"
    job.workspace = SimpleNamespace(openfile=openfile)

    try:
        raise RuntimeError("boom in finish")
    except RuntimeError as e:
        _record_finish_failure(job, e)

    # Status is untouched: the job keeps its canary_runtest outcome.
    assert job.status.outcome.name == "SUCCESS"
    assert job.status.category.value == "PASS"

    # The failure and its traceback are recorded to the job's output file.
    assert written, "expected the failure to be written to the job output file"
    output = written[0]
    assert "canary_runtest_finish hook failed" in output
    assert "RuntimeError: boom in finish" in output
