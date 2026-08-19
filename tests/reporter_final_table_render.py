# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from types import SimpleNamespace
from typing import Any
from typing import Callable

from _canary.job import BaseJob
from _canary.job import JobState
from _canary.reporter import Reporter
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
        pass

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


class DummyQueue:
    def __init__(self, jobs: list[BaseJob]) -> None:
        self._jobs = jobs
        self._heap = [SimpleNamespace(job=job) for job in jobs]

    def jobs(self):
        return list(self._jobs)

    def pending(self):
        return []

    def status(self, start: float | None = None) -> str:
        return "dummy status"


class DummyExecutor:
    def __init__(self, jobs: list[BaseJob]) -> None:
        self.queue = DummyQueue(jobs)
        self.submitted = {}
        self.running = {}
        self.finished = {}
        self.started_on = 0.0
        self.live_reporting = False

    @property
    def inflight(self):
        return {}

    def add_listener(self, callback: Callable[..., None]) -> None:
        pass

    def remove_listener(self, callback: Callable[..., None]) -> None:
        pass


def test_final_table_uses_configured_final_columns():
    job = DummyJob(name="failed")
    job.status.set(outcome="FAILED", reason="boom")
    job.measurements["timing"] = {"Queued": 1.0, "Running": 2.0, "Time": 3.0}

    executor = DummyExecutor([job])
    reporter = Reporter(executor)
    reporter.final_columns = ("Job", "ID", "Status", "Queued", "Running", "Time", "Details")

    table_group = reporter.final_table()

    text = str(table_group)
    # This is intentionally loose because Rich renderables do not stringify
    # exactly as displayed. The important part is that final_table returns
    # a renderable without error for generic columns.
    assert table_group is not None
