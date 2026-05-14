# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.job import BaseJob
from _canary.job import JobPhase
from _canary.job import JobState
from _canary.status import Status


def test_jobphase_values() -> None:
    assert JobPhase.PENDING.value == "PENDING"
    assert JobPhase.SUBMITTED.value == "SUBMITTED"
    assert JobPhase.RUNNING.value == "RUNNING"
    assert JobPhase.DONE.value == "DONE"


def test_jobstate_defaults_to_pending() -> None:
    s = JobState()
    assert s.phase is JobPhase.PENDING
    assert s.is_pending()
    assert not s.is_running()
    assert not s.is_done()


def test_jobstate_running() -> None:
    s = JobState(phase=JobPhase.RUNNING)
    assert not s.is_pending()
    assert s.is_running()
    assert not s.is_done()


def test_jobstate_done() -> None:
    s = JobState(phase=JobPhase.DONE)
    assert not s.is_pending()
    assert not s.is_running()
    assert s.is_done()


def test_basejob_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseJob()  # type: ignore[abstract]


def test_basejob_default_phase_transitions() -> None:

    class DummyJob(BaseJob):
        # Satisfy BaseJob abstract interface as loosely as possible for this test.
        id = "dummy"

        def __init__(self) -> None:
            self.state = JobState()

        def cost(self) -> float:
            return 1.0

        @property
        def status(self) -> "Status":
            raise NotImplementedError

        def required_resources(self):
            return [{"type": "cpus", "slots": 1}]

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
            return

        def save(self) -> None:
            return

        def display_name(self, **kwargs) -> str:
            return "DummyJob"

    job = DummyJob()
    assert job.state.phase is JobPhase.PENDING

    job.on_started()
    assert job.state.phase is JobPhase.RUNNING

    job.on_finished()
    assert job.state.phase is JobPhase.DONE


def test_basejob_validate_enqueuable_rejects_running_or_done() -> None:
    class DummyJob(BaseJob):
        id = "dummy"

        def __init__(self, phase: JobPhase) -> None:
            self.state = JobState(phase=phase)

        def cost(self) -> float:
            return 1.0

        @property
        def status(self) -> "Status":
            raise NotImplementedError

        def required_resources(self):
            return [{"type": "cpus", "slots": 1}]

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
            return

        def save(self) -> None:
            return

        def display_name(self, **kwargs) -> str:
            return "DummyJob"

    pending = DummyJob(JobPhase.PENDING)
    pending.validate_enqueuable()  # should not raise

    running = DummyJob(JobPhase.RUNNING)
    with pytest.raises(ValueError):
        running.validate_enqueuable()

    done = DummyJob(JobPhase.DONE)
    with pytest.raises(ValueError):
        done.validate_enqueuable()
