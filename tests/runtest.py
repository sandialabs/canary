# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for session-end reconciliation of unfinished jobs."""

from types import SimpleNamespace
from typing import Any

from _canary.job import BaseJob
from _canary.job import JobPhase
from _canary.job import JobState
from _canary.runtest import Runner
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
    job = DummyJob()  # phase PENDING, status unset
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


def test_reconcile_marks_running_job_broken():
    job = DummyJob()
    job.state.phase = JobPhase.RUNNING
    n = reconcile_unfinished_jobs(_runner([job]), interrupted=True)
    assert n == 1
    assert job.state.is_done()
    # A job that started but never reported is BROKEN regardless of interrupt.
    assert job.status.outcome.name == "BROKEN"
    assert job.status.category.value == "FAIL"


def test_reconcile_leaves_terminal_jobs_untouched():
    done = DummyJob()
    done.state.phase = JobPhase.DONE
    done.status.set(category="PASS", outcome="SUCCESS")
    n = reconcile_unfinished_jobs(_runner([done]), interrupted=True)
    assert n == 0
    assert done.status.outcome.name == "SUCCESS"
    assert not done.saved


def test_reconcile_mixed_batch_counts_only_unfinished():
    done = DummyJob(id="d" * 64)
    done.state.phase = JobPhase.DONE
    done.status.set(category="FAIL", outcome="FAILED")
    pending = DummyJob(id="p" * 64)
    running = DummyJob(id="r" * 64)
    running.state.phase = JobPhase.RUNNING

    n = reconcile_unfinished_jobs(_runner([done, pending, running]), interrupted=False)
    assert n == 2
    assert done.status.outcome.name == "FAILED"
    assert pending.status.outcome.name == "CANCELLED"
    assert running.status.outcome.name == "BROKEN"
    assert all(j.state.is_done() for j in (done, pending, running))
