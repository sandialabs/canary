# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import os
import shutil
import sys
import threading
import time
from typing import Literal

from rich import box
from rich import print as rprint
from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from . import config
from .job_queue import ExecutionSlot
from .job_queue import JobQueue
from .util import logging

logger = logging.get_logger(__name__)


class Reporter:
    def __init__(self, executor: JobQueue) -> None:
        self.executor = executor
        style = config.getoption("console_style") or {}
        self.namefmt = style.get("name", "short")
        self.live_columns: tuple[str, ...]
        if "live_columns" in style:
            cols = style["live_columns"]
            self.live_columns = tuple(cols.split(","))
        else:
            self.live_columns = ("Job", "ID", "Status", "Elapsed", "Rank")
        self.final_columns: tuple[str, ...] = (
            "Job",
            "ID",
            "Status",
            "Elapsed",
            "Details",
        )
        self.validate_columns(self.live_columns)
        self.validate_columns(self.final_columns)

    def validate_columns(self, columns: tuple[str, ...]) -> None:
        choices = (
            "Job",
            "ID",
            "Status",
            "Queued",
            "Running",
            "Elapsed",
            "Rank",
            "Details",
        )
        for col in columns:
            if col not in choices:
                s = ",".join(choices)
                raise ValueError(f"Illegal column name: {col}, choose from {s}")

    def add_table_columns(self, table: Table, columns: tuple[str, ...]) -> None:
        for name in columns:
            kwds = {}
            if name == "Job":
                kwds["overflow"] = "fold"
            elif name == "Details":
                kwds["overflow"] = "ellipsis"
            elif name in ("Queued", "Elapsed", "Running"):
                kwds["justify"] = "right"
            table.add_column(name, **kwds)

    def add_table_row(self, table: Table, columns: tuple[str, ...], **kwargs: str) -> None:
        row: list[str] = []
        for name in columns:
            row.append(kwargs.get(name.lower(), ""))
        table.add_row(*row)

    def final_table(self) -> Group:
        xtor = self.executor
        jobs = xtor.jobs()
        text = xtor.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
        table = Table(expand=False, box=box.SQUARE)
        self.add_table_columns(table, self.final_columns)
        for job in jobs:
            if job.status.is_success():
                continue
            self.add_table_row(
                table,
                self.final_columns,
                job=job.display_name(style="rich", resolve=self.namefmt == "long"),
                id=job.id[:7],
                status=job.status.display_name(style="rich"),
                elapsed=fmt_secs(job.timekeeper.duration()),
                queued=fmt_secs(job.timekeeper.queued()),
                details=job.status.reason or "",
            )
        if not table.row_count:
            n = len(jobs)
            return Group(f"[blue]INFO[/]: {n}/{n} tests finished with status [bold green]PASS[/]")
        return Group(table, footer)


class LiveReporter(Reporter):
    def __init__(self, executor: JobQueue) -> None:
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
        text = xtor.status(start=xtor.started_on)
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

        recent_finished = [s for s in xtor.finished.values() if now - s.finished < decay_window]

        # Most recent first
        recent_finished.sort(key=lambda s: s.finished, reverse=True)
        for slot in recent_finished[:max_finished]:
            if rows_used >= max_rows:
                break
            self.add_table_row(
                table,
                self.live_columns,
                job=slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
                id=slot.job.id[:7],
                status=slot.job.status.display_name(style="rich"),
                queued=fmt_secs(slot.queued()),
                elapsed=fmt_secs(slot.elapsed()),
                rank=f"{slot.qrank}/{slot.qsize}",
            )
            rows_used += 1

        # ---------------------------------------------------------
        # 2) RUNNING (longest-running first for stability)
        # ---------------------------------------------------------
        running = sorted(xtor.running.values(), key=lambda s: s.running(), reverse=True)
        for slot in running:
            if rows_used >= max_rows:
                break
            self.add_table_row(
                table,
                self.live_columns,
                job=slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
                id=slot.job.id[:7],
                status="[green]RUNNING[/]",
                queued=fmt_secs(slot.queued()),
                elapsed=fmt_secs(slot.elapsed()),
                rank=f"{slot.qrank}/{slot.qsize}",
            )
            rows_used += 1

        # ---------------------------------------------------------
        # 3) SUBMITTED
        # ---------------------------------------------------------
        submitted = sorted(xtor.submitted.values(), key=lambda s: s.qrank)
        for slot in submitted:
            if rows_used >= max_rows:
                break
            self.add_table_row(
                table,
                self.live_columns,
                job=slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
                id=slot.job.id[:7],
                status="[cyan]SUBMITTED[/]",
                queued=fmt_secs(slot.elapsed()),
                elapsed=fmt_secs(slot.elapsed()),
                rank=f"{slot.qrank}/{slot.qsize}",
            )
            rows_used += 1

        # ---------------------------------------------------------
        # 4) PENDING
        # ---------------------------------------------------------
        if rows_used < max_rows:
            for job in xtor.pending():
                if rows_used >= max_rows:
                    break
                self.add_table_row(
                    table,
                    self.live_columns,
                    job=job.display_name(style="rich", resolve=self.namefmt == "long"),
                    id=job.id[:7],
                    status="[magenta]PENDING[/]",
                    queued="NA",
                    elapsed="NA",
                    rank="",
                )
                rows_used += 1

        if not table.row_count:
            return Group("")

        return Group(table, footer)


class EventReporter(Reporter):
    def __init__(self, executor: JobQueue) -> None:
        super().__init__(executor)
        self.table = StaticTable()
        maxnamelen: int = -1
        for s in executor.inflight.values():
            name = s.job.display_name(resolve=self.namefmt == "long")
            maxnamelen = max(maxnamelen, len(name))
        if var := os.getenv("COLUMNS"):
            columns = int(var)
        else:
            columns = shutil.get_terminal_size().columns
        n = 8
        used = maxnamelen + 4 * 8
        avail = columns - used
        if avail < 0:
            n = 4
            status_width = 15
        else:
            status_width = min(max(avail, 30), 45)
        self.table.add_column("Job", width=maxnamelen)
        self.table.add_column("ID", width=n)
        self.table.add_column("Status", width=status_width)
        # self.table.add_column("Queued", width=n, align="right")
        self.table.add_column("Elapsed", width=n, align="right")
        self.table.add_column("Rank", width=n, align="right")

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

    def on_job_submit(self, slot: ExecutionSlot) -> None:
        row = [
            slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
            slot.job.id[:7],
            "[cyan]SUBMITTED[/]",
            # "",
            "",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_start(self, slot: ExecutionSlot) -> None:
        row = [
            slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
            slot.job.id[:7],
            "[blue]STARTED[/]",
            # fmt_secs(slot.queued()),
            "",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_finish(self, slot: ExecutionSlot) -> None:
        row = [
            slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
            slot.job.id[:7],
            slot.job.status.display_name(style="rich"),
            # fmt_secs(slot.queued()),
            fmt_secs(slot.elapsed()),
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
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
