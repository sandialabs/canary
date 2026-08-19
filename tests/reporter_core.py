# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from types import SimpleNamespace
from typing import Any
from typing import Callable
from typing import cast

import pytest

from _canary.job import BaseJob
from _canary.job import JobState
from _canary.queue_executor import ExecutionSlot
from _canary.reporter import EventReporter
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
        self._status.set(outcome="SUCCESS")
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

    def display_name(self, **kwargs: Any) -> str:
        if kwargs.get("style") == "rich":
            return self.name
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

    def jobs(self) -> list[BaseJob]:
        return list(self._jobs)

    def pending(self) -> list[BaseJob]:
        return []

    def status(self, start: float | None = None) -> str:
        return "dummy status"


class DummyExecutor:
    def __init__(self, jobs: list[BaseJob]) -> None:
        self.queue = DummyQueue(jobs)
        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}
        self.started_on = 0.0
        self.live_reporting = False
        self.listeners: list[Callable[..., None]] = []

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    def add_listener(self, callback: Callable[..., None]) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[..., None]) -> None:
        self.listeners.remove(callback)


def make_slot() -> ExecutionSlot:
    job = DummyJob(name="myjob")
    slot = ExecutionSlot(job=cast(BaseJob, job), qrank=2, qsize=5, worker_id=0)

    slot.timer.start("Queued", at=10.0)
    slot.timer.transition("Startup", at=11.0)
    slot.timer.transition("Running", at=14.0)
    slot.timer.transition("Teardown", at=20.0)
    slot.timer.stop(at=21.0)

    return slot


def test_reporter_timing_columns_are_non_metadata() -> None:
    job = DummyJob()
    reporter = Reporter(DummyExecutor([job]))

    columns = ("Job", "ID", "Status", "Queued", "Startup", "Running", "Teardown", "Time", "Rank")

    assert reporter.timing_columns(columns) == ("Queued", "Startup", "Running", "Teardown", "Time")


def test_reporter_time_column_totals_all_phases_when_no_explicit_phase_columns() -> None:
    job = DummyJob()
    reporter = Reporter(DummyExecutor([job]))
    slot = make_slot()

    # With only Time configured, it should total all recorded phases.
    assert reporter.slot_time_for_column(slot, "Time", ("Job", "Time")) == pytest.approx(11.0)


def test_reporter_time_column_totals_configured_phase_columns() -> None:
    job = DummyJob()
    reporter = Reporter(DummyExecutor([job]))
    slot = make_slot()

    columns = ("Job", "Queued", "Running", "Time")
    assert reporter.slot_time_for_column(slot, "Time", columns) == pytest.approx(7.0)


def test_reporter_row_values_for_slot_are_column_driven() -> None:
    job = DummyJob()
    reporter = Reporter(DummyExecutor([job]))
    slot = make_slot()

    columns = ("Job", "ID", "Status", "Queued", "Startup", "Running", "Teardown", "Time", "Rank")
    values = reporter.row_values_for_slot(slot, columns, status="[green]RUNNING[/]")

    assert values["job"] == "myjob"
    assert values["id"] == "aaaaaaaa"[:7]
    assert values["status"] == "[green]RUNNING[/]"
    assert values["queued"].strip().endswith("s")
    assert values["startup"].strip().endswith("s")
    assert values["running"].strip().endswith("s")
    assert values["teardown"].strip().endswith("s")
    assert values["time"].strip().endswith("s")
    assert values["rank"] == "2/5"


def test_reporter_pending_rows_mark_timing_columns_na() -> None:
    job = DummyJob(name="pending")
    reporter = Reporter(DummyExecutor([job]))

    columns = ("Job", "ID", "Status", "Queued", "Running", "Time", "Rank")
    values = reporter.row_values_for_pending_job(job, columns)

    assert values["queued"] == "NA"
    assert values["running"] == "NA"
    assert values["time"] == "NA"
    assert values["status"] == "[magenta]PENDING[/]"


def test_event_reporter_uses_compact_event_columns() -> None:
    job = DummyJob(name="event")
    reporter = EventReporter(DummyExecutor([job]))

    assert reporter.event_columns == ("Job", "ID", "Status", "Time", "Rank")
    assert [col.header for col in reporter.table.columns] == list(reporter.event_columns)


def test_event_reporter_renders_event_row_with_time() -> None:
    job = DummyJob(name="event")
    reporter = EventReporter(DummyExecutor([job]))
    slot = make_slot()

    text = reporter.render_event_row(slot, status="[cyan]SUBMITTED[/]")

    rendered = text.plain
    assert "myjob" in rendered
    assert "SUBMITTED" in rendered
    assert "2/5" in rendered


def test_row_values_for_job_uses_generic_timing_measurements():
    job = DummyJob(name="bad")
    job.status.set(outcome="FAILED", reason="boom")
    job.measurements["timing"] = {
        "Queued": 1.0,
        "Startup": 2.0,
        "Running": 3.0,
        "Teardown": 4.0,
        "Time": 10.0,
    }

    reporter = Reporter(DummyExecutor([job]))
    columns = ("Job", "ID", "Status", "Queued", "Startup", "Running", "Teardown", "Time", "Details")

    values = reporter.row_values_for_job(job, columns)

    assert values["job"] == "bad"
    assert values["status"].endswith("[/]") or "FAIL" in values["status"]
    assert values["queued"].strip() == "1.0s"
    assert values["startup"].strip() == "2.0s"
    assert values["running"].strip() == "3.0s"
    assert values["teardown"].strip() == "4.0s"
    assert values["time"].strip() == "10.0s"
    assert values["details"] == "boom"


def test_row_values_for_job_falls_back_to_timekeeper():
    job = DummyJob(name="bad")
    job.status.set(outcome="FAILED", reason="boom")
    job.timekeeper.submitted = 1.0
    job.timekeeper.started = 3.0
    job.timekeeper.finished = 8.0

    reporter = Reporter(DummyExecutor([job]))
    columns = ("Job", "ID", "Status", "Queued", "Running", "Time", "Details")

    values = reporter.row_values_for_job(job, columns)

    assert values["queued"].strip() == "2.0s"
    assert values["running"].strip() == "5.0s"
    assert values["time"].strip() == "7.0s"
