# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import time
from typing import Any
from typing import cast

import pytest

from _canary.job import BaseJob
from _canary.job import JobState
from _canary.queue_executor import ExecutionSlot
from _canary.queue_executor import PhaseTimer
from _canary.status import Status
from _canary.timekeeper import Timekeeper


class DummyJob(BaseJob):
    id = "dummy"

    def __init__(self) -> None:
        self.name = "dummy"
        self.state = JobState()
        self.timekeeper = Timekeeper()
        self._status = Status()
        self.saved = False
        self.refreshed = False

    @property
    def status(self) -> Status:
        return self._status

    def cost(self) -> float:
        return 1.0

    def required_resources(self):
        return []

    def assign_resources(self, arg):
        self._resources = arg

    def free_resources(self):
        return getattr(self, "_resources", {})

    def refresh_readiness(self) -> None:
        return

    def is_runnable(self) -> bool:
        return True

    def is_ready(self) -> bool:
        return True

    def total_timeout(self) -> float:
        return 1.0

    def refresh(self) -> None:
        self.refreshed = True

    def save(self) -> None:
        self.saved = True

    def display_name(self, **kwargs: Any) -> str:
        return self.name

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(category=category, outcome=outcome, reason=reason, code=code)


def test_phase_timer_explicit_transitions() -> None:
    timer = PhaseTimer()

    timer.start("Queued", at=10.0)
    timer.transition("Startup", at=12.0)
    timer.transition("Running", at=15.0)
    timer.transition("Teardown", at=20.0)
    timer.stop(at=21.0)

    assert timer.value("Queued", live=False) == pytest.approx(2.0)
    assert timer.value("Startup", live=False) == pytest.approx(3.0)
    assert timer.value("Running", live=False) == pytest.approx(5.0)
    assert timer.value("Teardown", live=False) == pytest.approx(1.0)
    assert timer.total(live=False) == pytest.approx(11.0)
    assert timer.current is None


def test_phase_timer_live_current_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    timer = PhaseTimer()
    timer.start("Queued", at=100.0)

    monkeypatch.setattr(time, "time", lambda: 106.5)

    assert timer.value("Queued") == pytest.approx(6.5)
    assert timer.total() == pytest.approx(6.5)


def test_phase_timer_repeated_phase_accumulates() -> None:
    timer = PhaseTimer()

    timer.start("Queued", at=0.0)
    timer.transition("Running", at=2.0)
    timer.transition("Queued", at=5.0)
    timer.transition("Running", at=7.0)
    timer.stop(at=11.0)

    assert timer.value("Queued", live=False) == pytest.approx(4.0)
    assert timer.value("Running", live=False) == pytest.approx(7.0)
    assert timer.total(live=False) == pytest.approx(11.0)


def test_phase_timer_start_resets_previous_state() -> None:
    timer = PhaseTimer()

    timer.start("Queued", at=0.0)
    timer.transition("Running", at=1.0)
    assert timer.value("Queued", live=False) == pytest.approx(1.0)

    timer.start("New", at=10.0)

    assert timer.value("Queued", live=False) == -1.0
    assert timer.value("Running", live=False) == -1.0
    assert timer.current == "New"


def test_execution_slot_default_timer_starts_queued() -> None:
    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    assert slot.phase_time("Queued") >= 0.0
    assert slot.phase_time("Running") == -1.0


def test_execution_slot_lifecycle_methods_update_job_and_timer() -> None:
    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    slot.timer.start("Queued", at=10.0)
    slot.on_submitted(10.0)
    slot.on_started(12.0)
    slot.on_finished(17.0)

    assert job.timekeeper.submitted == 10.0
    assert job.timekeeper.started == 12.0
    assert job.timekeeper.finished == 17.0
    assert job.state.is_done()

    assert slot.phase_time("Queued", live=False) == pytest.approx(2.0)
    assert slot.phase_time("Running", live=False) == pytest.approx(5.0)
    assert slot.total_time(live=False) == pytest.approx(7.0)


def test_execution_slot_total_time_subset() -> None:
    job = DummyJob()
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=1, qsize=1, worker_id=0)

    slot.timer.start("Queued", at=0.0)
    slot.timer.transition("Startup", at=1.0)
    slot.timer.transition("Running", at=3.0)
    slot.timer.transition("Teardown", at=8.0)
    slot.timer.stop(at=10.0)

    assert slot.total_time(("Queued", "Running"), live=False) == pytest.approx(6.0)
    assert slot.total_time(("Startup", "Teardown"), live=False) == pytest.approx(4.0)
