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
    timing_columns = {"Pending", "Staging", "Queued", "Running", "Finishing", "Elapsed", "Total"}

    def __init__(
        self, executor: ReporterExecutorProtocol, live_columns: str | Sequence[str] | None = None
    ) -> None:
        self.executor = executor
        style = config.getoption("console_style") or {}
        self.namefmt = style.get("name", "short")

        self.live_columns: tuple[str, ...]
        if live_columns is not None:
            self.live_columns = self.expand_column_name_shortcuts(list(live_columns))
        elif "live_columns" in style:
            self.live_columns = self.expand_column_name_shortcuts(
                [col.strip() for col in style["live_columns"].split(",")]
            )
        else:
            self.live_columns = ("Job", "ID", "Status", "Running", "Rank")
        self.validate_columns(self.live_columns)

        self.final_columns: tuple[str, ...]
        if "final_columns" in style:
            self.final_columns = tuple(col.strip() for col in style["final_columns"].split(","))
        else:
            self.final_columns = ("Job", "ID", "Status", "Total", "Details")
        self.validate_columns(self.final_columns)

    def job_time_for_column(self, job: BaseJob, column: str) -> float:
        """
        Return persisted timing for a finished job.

        """
        tk = job.timekeeper
        match column:
            case "Pending" | "Queued":
                return tk.pending(live=True)
            case "Staging" | "Startup":
                return tk.staging(live=True)
            case "Running":
                return tk.running(live=True)
            case "Finishing" | "Teardown":
                return tk.finishing(live=True)
            case "Total":
                return tk.total(live=True)
            case "Elapsed":
                return tk.elapsed(live=True)
        return -1.0

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

        for column in self.timing_columns:
            values[column.lower()] = fmt_secs(self.job_time_for_column(slot.job, column))

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

        for column in self.timing_columns:
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

        for column in self.timing_columns:
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
            if col in self.timing_columns:
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
            elif name in self.timing_columns:
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

        # Group jobs by status category.  Non-pass categories come first so
        # failures are always visible at the top; PASS is printed last.
        # Within each category the insertion order (== execution order) is kept.
        from collections import defaultdict

        from _canary.status import Category

        _CATEGORY_ORDER = [
            Category.FAIL,
            Category.CANCEL,
            Category.SKIP,
            Category.NONE,
            Category.PASS,
        ]
        _MAX_PER_CATEGORY = 10

        by_category: dict = defaultdict(list)
        for job in jobs:
            by_category[job.status.category].append(job)

        table = Table(expand=False, box=box.SQUARE)
        self.add_table_columns(table, self.final_columns)

        for category in _CATEGORY_ORDER:
            group = by_category.get(category, [])
            if not group:
                continue
            shown = group[:_MAX_PER_CATEGORY]
            remainder = len(group) - len(shown)
            for job in shown:
                values = self.row_values_for_job(job, self.final_columns)
                self.add_table_row_from_values(table, self.final_columns, values)
            if remainder:
                # Ellipsis row: blank all columns except "Job" which carries the note.
                ellipsis_values: dict[str, str] = {col.lower(): "" for col in self.final_columns}
                ellipsis_values["job"] = (
                    f"[dim]... {remainder} more {category.value} job{'s' if remainder != 1 else ''}"
                    f" — run [italic]canary status[/] for the full list[/]"
                )
                self.add_table_row_from_values(table, self.final_columns, ellipsis_values)

        return Group(table, footer)

    def expand_column_name_shortcuts(self, args: Sequence[str]) -> tuple[str, ...]:
        column_names: list[str] = []
        for arg in args:
            match arg.lower():
                case "j" | "job":
                    column_names.append("Job")
                case "i" | "id":
                    column_names.append("ID")
                case "x" | "status":
                    column_names.append("Status")
                case "w" | "rank":
                    column_names.append("Rank")
                case "d" | "details":
                    column_names.append("Details")
                case "p" | "pending":
                    column_names.append("Pending")
                case "s" | "staging":
                    column_names.append("Staging")
                case "q" | "queued":
                    column_names.append("Queued")
                case "r" | "running":
                    column_names.append("Running")
                case "f" | "finishing":
                    column_names.append("Finishing")
                case "e" | "elapsed":
                    column_names.append("Elapsed")
                case "t" | "total":
                    column_names.append("Total")
                case _:
                    raise ValueError(f"Unknown column name: {arg}")
        return tuple(column_names)


class _LiveConsoleHandler(logging.builtin_logging.Handler):
    """Logging handler that writes records through a Rich ``Console``.

    Installed by :class:`LiveReporter` in place of the normal stream handlers
    while the live table is active.  Rich's ``Console.log()`` knows to print
    *above* (i.e. before rewinding) the live display, so warnings and
    diagnostics appear in-scroll rather than being hidden or corrupting the
    table.

    Only records at or above *min_level* are forwarded; records below that
    threshold (e.g. DEBUG during a default-INFO run) are silently dropped,
    preserving the behaviour of the original stream handler's level filter.
    """

    def __init__(self, console: Console, min_level: int) -> None:
        super().__init__(level=min_level)
        self._console = console

    def emit(self, record: logging.builtin_logging.LogRecord) -> None:
        try:
            # Re-use the canary Formatter to get the colored level prefix.
            msg = self.format(record)
            self._console.log(msg, markup=True, highlight=False)
        except Exception:  # nosec B110
            self.handleError(record)


class LiveReporter(Reporter):
    def __init__(self, executor: ReporterExecutorProtocol, **kwargs: Any) -> None:
        super().__init__(executor, **kwargs)
        console = Console(file=sys.stdout, force_terminal=True)
        self.live = Live(refresh_per_second=1, console=console, transient=False, auto_refresh=False)
        self._filter = logging.MuteConsoleFilter()
        self._stream_handlers: list[logging.builtin_logging.StreamHandler] = []
        self._live_handlers: list[_LiveConsoleHandler] = []
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
        """Replace terminal stream handlers with Rich-aware equivalents.

        For each **terminal** ``StreamHandler`` found on the canary and root
        loggers (file handlers are explicitly excluded — see below):

        1. Attach the ``MuteConsoleFilter`` to silence its normal output
           (prevents raw text from leaking around the live display).
        2. Install a ``_LiveConsoleHandler`` on the *same logger* that routes
           records through ``live.console.log()``, which Rich renders above the
           live table without corrupting it.

        The pairing is recorded so :meth:`unmute_stream_handlers` can undo both
        operations in the right order.

        .. note::
            ``logging.FileHandler`` is a subclass of ``logging.StreamHandler``
            in the stdlib, so it would match a plain ``isinstance`` check.  We
            skip file handlers explicitly so that ``canary.0.log`` continues to
            receive all log records unmodified throughout the run — only the
            terminal (stderr/stdout) stream is redirected through Rich.
        """
        for logger_name in (logging.root_log_name, ""):
            root = logging.builtin_logging.getLogger(logger_name)
            for h in root.handlers:
                # Only intercept pure stream (terminal) handlers — NOT file
                # handlers.  FileHandler is a subclass of StreamHandler, so
                # we must explicitly exclude it to ensure log records continue
                # flowing to canary.0.log unmodified during the live display.
                if isinstance(h, logging.builtin_logging.FileHandler):
                    continue
                if not isinstance(h, logging.builtin_logging.StreamHandler):
                    continue
                # 1. Silence the original handler.
                h.addFilter(self._filter)
                h.flush()
                self._stream_handlers.append(h)
                # 2. Add a Rich-aware handler at the same level.
                rich_h = _LiveConsoleHandler(self.live.console, h.level)
                # Copy the canary formatter so the level prefix/colour is preserved.
                if h.formatter is not None:
                    rich_h.setFormatter(h.formatter)
                root.addHandler(rich_h)
                self._live_handlers.append(rich_h)

    def unmute_stream_handlers(self) -> None:
        """Restore the original stream handlers and remove Rich-aware ones."""
        for h in self._stream_handlers:
            h.removeFilter(self._filter)
        self._stream_handlers.clear()

        for logger_name in (logging.root_log_name, ""):
            root = logging.builtin_logging.getLogger(logger_name)
            for rich_h in self._live_handlers:
                root.removeHandler(rich_h)
        self._live_handlers.clear()

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
            s for s in xtor.finished.values() if now - s.job.timekeeper._stopped < decay_window
        ]
        recent_finished.sort(key=lambda s: s.job.timekeeper._stopped, reverse=True)
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
        running = sorted(
            xtor.running.values(), key=lambda s: s.job.timekeeper.total(), reverse=True
        )
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

        self.debug = bool(config.get("debug"))
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
            elif col in self.timing_columns:
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
            case "job_staged":
                self.on_job_stage(args[0])
            case "job_started":
                self.on_job_start(args[0])
            case "job_stopped":
                self.on_job_stop(args[0])
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

    def on_job_stage(self, slot: "ExecutionSlot") -> None:
        if self.debug:
            text = self.render_event_row(slot, status="[blue]STAGING[/]")
            logger.info(text.markup, extra={"prefix": ""})

    def on_job_start(self, slot: "ExecutionSlot") -> None:
        text = self.render_event_row(slot, status="[blue]STARTED[/]")
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_stop(self, slot: "ExecutionSlot") -> None:
        if self.debug:
            text = self.render_event_row(slot, status="[blue]FINALIZING[/]")
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


def fmt_secs(x: float) -> str:
    """Format a duration in seconds as ``HH:MM:SS``.

    Uses :func:`_canary.util.time.hhmmss` so the seconds field is always
    present at every magnitude — a monotonically-ticking seconds digit is
    the cheapest liveness signal for a running job and must never be dropped.

    Negative inputs (used internally to signal "not yet measured") render as
    ``"--:--:--"``.
    """
    from _canary.util.time import hhmmss

    return hhmmss(None if x < 0 else x)
