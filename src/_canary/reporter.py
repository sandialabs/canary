# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import sys
import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Literal
from typing import Protocol

from rich import box
from rich import print as rprint
from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from . import config
from .job import BaseJob
from .util import logging

if TYPE_CHECKING:
    from .queue_executor import ExecutionSlot


logger = logging.get_logger(__name__)


class ReporterQueueProtocol(Protocol):
    _heap: list[Any]

    def jobs(self) -> Sequence[BaseJob]: ...

    def pending(self) -> Sequence[BaseJob]: ...

    def status(self, start: float | None = None) -> str: ...


class ReporterExecutorProtocol(Protocol):
    submitted: dict[str, "ExecutionSlot"]
    running: dict[str, "ExecutionSlot"]
    finished: dict[str, "ExecutionSlot"]
    started_on: float
    live_reporting: bool

    @property
    def queue(self) -> ReporterQueueProtocol: ...

    @property
    def inflight(self) -> dict[str, "ExecutionSlot"]: ...

    def add_listener(self, callback: Callable[..., None]) -> None: ...

    def remove_listener(self, callback: Callable[..., None]) -> None: ...


class Reporter:
    metadata_columns = {"Job", "ID", "Status", "Rank", "Details"}
    total_time_columns = {"Elapsed", "Time"}

    def __init__(self, executor: ReporterExecutorProtocol) -> None:
        self.executor = executor
        style = config.getoption("console_style") or {}
        self.namefmt = style.get("name", "short")

        self.live_columns: tuple[str, ...]
        if "live_columns" in style:
            self.live_columns = tuple(col.strip() for col in style["live_columns"].split(","))
        else:
            self.live_columns = ("Job", "ID", "Status", "Queued", "Running", "Elapsed", "Rank")
        self.validate_columns(self.live_columns)

        self.final_columns: tuple[str, ...]
        if "final_columns" in style:
            self.final_columns = tuple(col.strip() for col in style["final_columns"].split(","))
        else:
            self.final_columns = ("Job", "ID", "Status", "Queued", "Running", "Elapsed", "Details")
        self.validate_columns(self.final_columns)

    def timing_columns(self, columns: tuple[str, ...]) -> tuple[str, ...]:
        """
        Return configured timing columns.

        Any non-metadata column is considered a timer phase column, except
        Elapsed, which is computed as the total of the other timing columns.
        """
        return tuple(col for col in columns if col not in self.metadata_columns)

    def elapsed_phase_columns(self, columns: tuple[str, ...]) -> tuple[str, ...]:
        """
        Return timing phase columns included in Elapsed.

        Elapsed is not itself a phase; it is the total of the other timing
        columns in the configured column set.
        """
        return tuple(
            col for col in self.timing_columns(columns) if col not in self.total_time_columns
        )

    def slot_time_for_column(
        self, slot: "ExecutionSlot", column: str, columns: tuple[str, ...]
    ) -> float:
        if column in self.total_time_columns:
            phases = tuple(
                col for col in self.timing_columns(columns) if col not in self.total_time_columns
            )
            return slot.total_time(phases or None)

        return slot.phase_time(column)

    def job_time_for_column(self, job: BaseJob, column: str) -> float:
        """
        Return persisted timing for a finished job.

        This reads job.measurements["timing"] or job.measurements["flux_timing"]
        if available. Falls back to job.timekeeper for Running/Elapsed.
        """
        # Prefer a generic timing measurement if present.
        value = self._job_measurement(job, "timing", column)
        if isinstance(value, (int, float)):
            return float(value)

        # Also support lower-case/snake-case keys from existing flux_timing.
        keymap = {
            "Queued": "queue_time",
            "Startup": "startup_time",
            "Running": "execution_time",
            "Teardown": "teardown_time",
            "Elapsed": "elapsed_time",
        }
        if column in keymap:
            value = self._job_measurement(job, "flux_timing", keymap[column])
            if isinstance(value, (int, float)):
                return float(value)

        if column == "Running":
            return job.timekeeper.running()

        if column == "Queued":
            return job.timekeeper.queued()

        if column in self.total_time_columns:
            return job.timekeeper.total()

        return -1.0

    def _job_measurement(self, job: BaseJob, *path: str) -> Any:
        measurements = getattr(job, "measurements", None)
        if measurements is None:
            return None

        data: Any
        if hasattr(measurements, "data"):
            data = measurements.data
        else:
            data = measurements

        for key in path:
            if not isinstance(data, dict):
                return None
            data = data.get(key)

        return data

    def row_values_for_slot(
        self, slot: "ExecutionSlot", columns: tuple[str, ...], *, status: str, details: str = ""
    ) -> dict[str, str]:
        values: dict[str, str] = {
            "job": slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
            "id": slot.job.id[:7],
            "status": status,
            "rank": f"{slot.qrank}/{slot.qsize}",
            "details": details,
        }

        for column in self.timing_columns(columns):
            values[column.lower()] = fmt_secs(self.slot_time_for_column(slot, column, columns))

        return values

    def row_values_for_job(
        self, job: BaseJob, columns: tuple[str, ...], *, details: str | None = None
    ) -> dict[str, str]:
        values: dict[str, str] = {
            "job": job.display_name(style="rich", resolve=self.namefmt == "long"),
            "id": job.id[:7],
            "status": job.status.display_name(style="rich"),
            "rank": "",
            "details": details if details is not None else (job.status.reason or ""),
        }

        for column in self.timing_columns(columns):
            values[column.lower()] = fmt_secs(self.job_time_for_column(job, column))

        return values

    def row_values_for_pending_job(self, job: BaseJob, columns: tuple[str, ...]) -> dict[str, str]:
        values: dict[str, str] = {
            "job": job.display_name(style="rich", resolve=self.namefmt == "long"),
            "id": job.id[:7],
            "status": "[magenta]PENDING[/]",
            "rank": "",
            "details": "",
        }

        for column in self.timing_columns(columns):
            values[column.lower()] = "NA"

        return values

    def add_table_row_from_values(
        self, table: Table, columns: tuple[str, ...], values: dict[str, str]
    ) -> None:
        table.add_row(*(values.get(name.lower(), "") for name in columns))

    def format_row_values(self, columns: tuple[str, ...], values: dict[str, str]) -> list[str]:
        return [values.get(name.lower(), "") for name in columns]

    def validate_columns(self, columns: tuple[str, ...]) -> None:
        for col in columns:
            if col in self.metadata_columns:
                continue
            if col in self.total_time_columns:
                continue
            # Any other valid identifier-like label is treated as a timing phase.
            normalized = col.replace("_", "").replace("-", "")
            if not normalized.isalnum():
                raise ValueError(f"Illegal column name: {col!r}")

    def add_table_columns(self, table: Table, columns: tuple[str, ...]) -> None:
        for name in columns:
            kwds: dict[str, Any] = {}

            if name == "Job":
                kwds["overflow"] = "fold"
            elif name == "Details":
                kwds["overflow"] = "ellipsis"
            elif name in self.timing_columns(columns):
                kwds["justify"] = "right"
            elif name == "Rank":
                kwds["justify"] = "right"

            table.add_column(name, **kwds)

    def add_table_row(self, table: Table, columns: tuple[str, ...], **kwargs: str) -> None:
        row: list[str] = []
        for name in columns:
            row.append(kwargs.get(name.lower(), ""))
        table.add_row(*row)

    def final_table(self) -> Group:
        xtor = self.executor
        jobs = xtor.queue.jobs()
        text = xtor.queue.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
        table = Table(expand=False, box=box.SQUARE)
        self.add_table_columns(table, self.final_columns)
        for job in jobs:
            if job.status.is_success():
                continue
            values = self.row_values_for_job(job, self.final_columns)
            self.add_table_row_from_values(table, self.final_columns, values)
        if not table.row_count:
            n = len(jobs)
            return Group(f"[blue]INFO[/]: {n}/{n} tests finished with status [bold green]PASS[/]")
        return Group(table, footer)


class LiveReporter(Reporter):
    def __init__(self, executor: ReporterExecutorProtocol) -> None:
        super().__init__(executor)
        console = Console(file=sys.stdout, force_terminal=True)
        self.live = Live(refresh_per_second=1, console=console, transient=False, auto_refresh=False)
        self._filter = logging.MuteConsoleFilter()
        self._stream_handlers: list[logging.builtin_logging.StreamHandler] = []
        self._stop = threading.Event()
        self.refresh_interval = 0.25

    def __enter__(self):
        self.mute_stream_handlers()
        self.live.__enter__()
        self._thread = threading.Thread(target=self._refresh, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        self._thread.join()
        self.live.update(self.final_table() or "", refresh=True)
        self.live.__exit__(exc_type, exc, tb)
        self.unmute_stream_handlers()

    def mute_stream_handlers(self) -> None:
        root = logging.builtin_logging.getLogger(logging.root_log_name)
        for h in root.handlers:
            if isinstance(h, logging.builtin_logging.StreamHandler):
                h.addFilter(self._filter)
                self._stream_handlers.append(h)
                h.flush()
        root = logging.builtin_logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.builtin_logging.StreamHandler):
                h.addFilter(self._filter)
                self._stream_handlers.append(h)
                h.flush()

    def unmute_stream_handlers(self) -> None:
        for h in self._stream_handlers:
            h.removeFilter(self._filter)
        self._stream_handlers.clear()

    def _refresh(self) -> None:
        while not self._stop.is_set():
            if self.executor.inflight:
                self.live.update(self.dynamic_table(), refresh=True)
            self._stop.wait(self.refresh_interval)

    def dynamic_table(self) -> Group:
        xtor = self.executor
        now = time.time()

        # ---- Footer ----
        text = xtor.queue.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)

        # ---- Main Table ----
        table = Table(expand=False, box=box.SQUARE)
        self.add_table_columns(table, self.live_columns)

        max_rows = 30
        rows_used = 0

        # ---------------------------------------------------------
        # 1) FINISHED (recent only, time-decay)
        # ---------------------------------------------------------
        decay_window = 8.0  # seconds to keep finished visible
        max_finished = 5  # hard cap

        recent_finished = [
            s for s in xtor.finished.values() if now - s.finished_at() < decay_window
        ]
        recent_finished.sort(key=lambda s: s.finished_at(), reverse=True)
        for slot in recent_finished[:max_finished]:
            if rows_used >= max_rows:
                break

            values = self.row_values_for_slot(
                slot,
                self.live_columns,
                status=slot.job.status.display_name(style="rich"),
                details=slot.job.status.reason or "",
            )
            self.add_table_row_from_values(table, self.live_columns, values)
            rows_used += 1

        # ---------------------------------------------------------
        # 2) RUNNING (longest-running first for stability)
        # ---------------------------------------------------------
        running = sorted(xtor.running.values(), key=lambda s: s.total_time(), reverse=True)
        for slot in running:
            if rows_used >= max_rows:
                break

            values = self.row_values_for_slot(slot, self.live_columns, status="[green]RUNNING[/]")
            self.add_table_row_from_values(table, self.live_columns, values)
            rows_used += 1

        # ---------------------------------------------------------
        # 3) SUBMITTED
        # ---------------------------------------------------------
        submitted = sorted(xtor.submitted.values(), key=lambda s: s.qrank)

        for slot in submitted:
            if rows_used >= max_rows:
                break

            values = self.row_values_for_slot(slot, self.live_columns, status="[cyan]SUBMITTED[/]")
            self.add_table_row_from_values(table, self.live_columns, values)
            rows_used += 1

        # ---------------------------------------------------------
        # 4) PENDING
        # ---------------------------------------------------------
        if rows_used < max_rows:
            for job in xtor.queue.pending():
                if rows_used >= max_rows:
                    break

                values = self.row_values_for_pending_job(job, self.live_columns)
                self.add_table_row_from_values(table, self.live_columns, values)
                rows_used += 1

        if not table.row_count:
            return Group("")

        return Group(table, footer)


class EventReporter(Reporter):
    def __init__(self, executor: ReporterExecutorProtocol) -> None:
        super().__init__(executor)

        self.event_columns: tuple[str, ...] = ("Job", "ID", "Status", "Time", "Rank")
        self.validate_columns(self.event_columns)

        self.table = StaticTable()

        maxnamelen = max(
            (len(s.job.display_name(resolve=self.namefmt == "long")) for s in executor.queue._heap),
            default=len("Job"),
        )

        for col in self.event_columns:
            if col == "Job":
                self.table.add_column(col, width=maxnamelen)
            elif col == "ID":
                self.table.add_column(col, width=8)
            elif col == "Status":
                self.table.add_column(col, width=15)
            elif col == "Rank":
                self.table.add_column(col, width=8, align="right")
            elif col in self.timing_columns(self.event_columns):
                self.table.add_column(col, width=8, align="right")
            else:
                self.table.add_column(col, width=10)

    def __enter__(self):
        self.executor.add_listener(self.on_event)
        self.table.print_header()
        return self

    def __exit__(self, exc_type, exc, tb):
        rprint(self.final_table())
        self.executor.remove_listener(self.on_event)

    def on_event(self, event: str, *args, **kwargs) -> None:
        match event:
            case "job_submitted":
                self.on_job_submit(args[0])
            case "job_started":
                self.on_job_start(args[0])
            case "job_finished":
                self.on_job_finish(args[0])
            case _:
                return

    def render_event_row(self, slot: "ExecutionSlot", *, status: str, details: str = "") -> Text:
        values = self.row_values_for_slot(slot, self.event_columns, status=status, details=details)
        row = self.format_row_values(self.event_columns, values)
        return self.table.render_row(row)

    def on_job_submit(self, slot: "ExecutionSlot") -> None:
        text = self.render_event_row(slot, status="[cyan]SUBMITTED[/]")
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_start(self, slot: "ExecutionSlot") -> None:
        text = self.render_event_row(slot, status="[blue]STARTED[/]")
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_finish(self, slot: "ExecutionSlot") -> None:
        text = self.render_event_row(
            slot,
            status=slot.job.status.display_name(style="rich"),
            details=slot.job.status.reason or "",
        )
        logger.info(text.markup, extra={"prefix": ""})


@dataclasses.dataclass
class StaticColumn:
    header: str
    width: int
    align: Literal["left", "right"] = "left"


class StaticTable:
    def __init__(self, columns: list[StaticColumn] | None = None) -> None:
        self.columns = list(columns or [])

    def add_column(self, header: str, width: int, align: Literal["left", "right"] = "left") -> None:
        self.columns.append(StaticColumn(header=header, width=width, align=align))

    def _format_cell(self, value: str, col: StaticColumn) -> Text:
        text = Text.from_markup(value)
        if text.cell_len > col.width:
            text.truncate(col.width, overflow="ellipsis")
        pad = col.width - text.cell_len
        if pad > 0:
            if col.align == "right":
                text = Text(" " * pad) + text
            else:
                text += Text(" " * pad)
        return text

    def render_header(self) -> Text:
        return self.render_row([col.header for col in self.columns])

    def render_row(self, values: list[str]) -> Text:
        row = Text()
        for value, col in zip(values, self.columns):
            row.append(self._format_cell(value, col))
            row.append("  ")
        return row

    def print_header(self):
        text = self.render_header()
        rule = "─" * (text.cell_len - 2)
        logger.info(text.markup, extra={"prefix": ""})
        logger.info(rule, extra={"prefix": ""})


def fmt_secs(x: float, *, na: str = "NA") -> str:
    if x < 0:
        return na
    return f"{x:5.1f}s"
