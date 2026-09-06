# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from types import SimpleNamespace
from typing import Any
from typing import Callable
from typing import cast

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

    slot.on_submit(at=10.0)
    slot.on_stage(at=11.0)
    slot.on_start(at=14.0)
    slot.on_stop(at=20.0)
    slot.on_finish(at=21.0)

    return slot


def test_reporter_timing_columns_are_known() -> None:
    job = DummyJob()
    reporter = Reporter(DummyExecutor([job]))

    assert {"Queued", "Staging", "Running", "Finishing", "Total", "Elapsed"} <= set(
        reporter.timing_columns
    )


def test_reporter_row_values_for_slot_are_column_driven() -> None:
    job = DummyJob()
    reporter = Reporter(DummyExecutor([job]))
    slot = make_slot()

    columns = ("Job", "ID", "Status", "Queued", "Staging", "Running", "Finishing", "Total", "Rank")
    values = reporter.row_values_for_slot(slot, columns, status="[green]RUNNING[/]")

    assert values["job"] == "myjob"
    assert values["id"] == "aaaaaaaa"[:7]
    assert values["status"] == "[green]RUNNING[/]"
    assert values["queued"].strip().endswith("s")
    assert values["staging"].strip().endswith("s")
    assert values["running"].strip().endswith("s")
    assert values["finishing"].strip().endswith("s")
    assert values["total"].strip().endswith("s")
    assert values["rank"] == "2/5"


def test_reporter_slot_timing_values_from_timekeeper() -> None:
    reporter = Reporter(DummyExecutor([DummyJob()]))
    slot = make_slot()
    values = reporter.row_values_for_slot(slot, ("Job",), status="RUNNING")

    assert values["queued"].strip() == "1.0s"
    assert values["staging"].strip() == "3.0s"
    assert values["running"].strip() == "6.0s"
    assert values["finishing"].strip() == "1.0s"
    assert values["total"].strip() == "11.0s"


def test_reporter_pending_rows_mark_timing_columns_na() -> None:
    job = DummyJob(name="pending")
    reporter = Reporter(DummyExecutor([job]))

    columns = ("Job", "ID", "Status", "Queued", "Running", "Total", "Rank")
    values = reporter.row_values_for_pending_job(job, columns)

    assert values["queued"] == "NA"
    assert values["running"] == "NA"
    assert values["total"] == "NA"
    assert values["status"] == "[magenta]PENDING[/]"


def test_event_reporter_uses_compact_event_columns() -> None:
    job = DummyJob(name="event")
    reporter = EventReporter(DummyExecutor([job]))

    assert reporter.event_columns == ("Job", "ID", "Status", "Time", "Rank")
    assert [col.header for col in reporter.table.columns] == list(reporter.event_columns)


def test_event_reporter_renders_event_row() -> None:
    job = DummyJob(name="event")
    reporter = EventReporter(DummyExecutor([job]))
    slot = make_slot()

    text = reporter.render_event_row(slot, status="[cyan]SUBMITTED[/]")

    rendered = text.plain
    assert "myjob" in rendered
    assert "SUBMITTED" in rendered
    assert "2/5" in rendered


def test_row_values_for_job_falls_back_to_timekeeper():
    job = DummyJob(name="bad")
    job.status.set(outcome="FAILED", reason="boom")
    job.timekeeper.open(at=1.0)
    job.timekeeper.stage(at=3.0)
    job.timekeeper.start(at=4.0)
    job.timekeeper.stop(at=8.0)
    job.timekeeper.close(at=10.0)

    reporter = Reporter(DummyExecutor([job]))
    columns = ("Job", "ID", "Status", "Queued", "Running", "Total", "Details")

    values = reporter.row_values_for_job(job, columns)

    assert values["job"] == "bad"
    assert values["status"].endswith("[/]") or "FAIL" in values["status"]
    assert values["queued"].strip() == "2.0s"
    assert values["running"].strip() == "4.0s"
    assert values["total"].strip() == "9.0s"
    assert values["details"] == "boom"


# ---------------------------------------------------------------------------
# Tests for _LiveConsoleHandler and LiveReporter log routing
# ---------------------------------------------------------------------------


def test_live_console_handler_emits_via_console():
    """_LiveConsoleHandler.emit() calls console.log() with the formatted message."""
    import logging as _logging
    from io import StringIO

    from rich.console import Console

    from _canary.reporter import _LiveConsoleHandler
    from _canary.util.logging import Formatter

    buf = StringIO()
    console = Console(file=buf, highlight=False, markup=True)
    handler = _LiveConsoleHandler(console, min_level=_logging.WARNING)
    handler.setFormatter(Formatter(color=False))

    record = _logging.LogRecord(
        name="canary",
        level=_logging.WARNING,
        pathname="",
        lineno=0,
        msg="something went wrong",
        args=(),
        exc_info=None,
    )
    handler.emit(record)

    output = buf.getvalue()
    assert "something went wrong" in output


def test_live_console_handler_level_respected_via_logger():
    """Records below _LiveConsoleHandler's level are not emitted when routed via logger."""
    import logging as _logging
    from io import StringIO

    from rich.console import Console

    from _canary.reporter import _LiveConsoleHandler
    from _canary.util.logging import Formatter

    buf = StringIO()
    console = Console(file=buf, highlight=False)
    handler = _LiveConsoleHandler(console, min_level=_logging.WARNING)
    handler.setFormatter(Formatter(color=False))

    # Wire the handler to a fresh logger so we control what reaches it.
    test_logger = _logging.getLogger("canary._test_level_check")
    test_logger.handlers.clear()
    test_logger.propagate = False
    test_logger.setLevel(_logging.DEBUG)
    test_logger.addHandler(handler)

    # DEBUG message: below WARNING threshold — handler.level filters it out.
    test_logger.debug("debug noise")
    assert buf.getvalue() == ""

    # WARNING message: at threshold — should pass through.
    test_logger.warning("important warning")
    assert "important warning" in buf.getvalue()

    # Clean up.
    test_logger.removeHandler(handler)


def test_mute_and_unmute_restores_handlers():
    """mute_stream_handlers adds _LiveConsoleHandler; unmute removes it cleanly."""
    import logging as _logging
    from io import StringIO
    from unittest.mock import MagicMock

    from _canary.reporter import LiveReporter

    # Build a minimal fake executor
    job = DummyJob()
    executor = DummyExecutor([job])

    reporter = LiveReporter(executor)

    # Capture console output in a buffer (avoids terminal requirement)
    buf = StringIO()
    from rich.console import Console

    reporter.live = MagicMock()
    reporter.live.console = Console(file=buf, highlight=False)

    root = _logging.getLogger()
    initial_handler_count = len(root.handlers)

    reporter.mute_stream_handlers()
    after_mute_count = len(root.handlers)

    reporter.unmute_stream_handlers()
    after_unmute_count = len(root.handlers)

    # After unmuting, handler count should be back to the initial value.
    assert after_unmute_count == initial_handler_count
    # During muting, at least one _LiveConsoleHandler should have been added
    # for each StreamHandler that was found (may be zero if root has none).
    assert after_mute_count >= initial_handler_count
