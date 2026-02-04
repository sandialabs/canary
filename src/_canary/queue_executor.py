# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import math
import os
import signal
import sys
import threading
import time
from functools import cached_property
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Literal

from rich import box
from rich import print as rprint
from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from . import config
from .error import StopExecution
from .protocols import JobProtocol
from .queue import Busy
from .queue import Empty
from .queue import ResourceQueue
from .util import cpu_count
from .util import logging
from .util import multiprocessing as mp
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)


EventTypes = Literal["job_submitted", "job_started", "job_finished"]


@dataclasses.dataclass
class ExecutionSlot:
    job: JobProtocol
    qrank: int
    qsize: int
    spawned: float
    proc: mp.MeasuredProcess
    queue: mp.SimpleQueue
    submitted: float = -1.0
    started: float = -1.0
    finished: float = -1.0


class JobFunctor:
    def __call__(
        self,
        executor: Callable,
        job: JobProtocol,
        result_queue: mp.SimpleQueue,
        logging_queue: mp.Queue,
        config_snapshot: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Process entrypoint: bootstraps environment and executes a single job."""
        config.load_snapshot(config_snapshot)
        logging.clear_handlers()
        h = logging.QueueHandler(logging_queue)
        logging.add_handler(h)
        try:
            executor(job, queue=result_queue, **kwargs)
        except BaseException as e:
            logger.exception(f"Job {job}: exception occurred during execution of job functor")
            job.set_status(status="ERROR", reason=f"{e.__class__.__name__}({e.args[0]})")
            sys.exit(1)
        else:
            logger.debug(f"Job {job}: job functor exited normally")
        finally:
            try:
                result_queue.put(("FINISHED", job.getstate()))
            except Exception:
                logger.exception("Failed to put job state into queue")
                raise
            finally:
                logging.clear_handlers()


class ResourceQueueExecutor:
    """Manages a pool of worker processes with timeout support and metrics collection."""

    def __init__(
        self,
        queue: ResourceQueue,
        executor: Callable,
        max_workers: int = -1,
        busy_wait_time: float = 0.05,
    ):
        """
        Initialize the process pool.

        Args:
            max_workers: Maximum number of concurrent worker processes
            queue: ResourceQueue instance
            executor: Callable that processes cases
            busy_wait_time: Time to wait when queue is busy
        """
        nproc = cpu_count()
        self.max_workers = max_workers if max_workers > 0 else math.ceil(0.85 * nproc)
        if self.max_workers > nproc:
            logger.warning(f"workers={self.max_workers} > cpu_count={nproc}")

        self.queue: ResourceQueue = queue
        self.executor = executor
        self.busy_wait_time = busy_wait_time

        self.submitted: dict[int, ExecutionSlot] = {}
        self.running: dict[int, ExecutionSlot] = {}
        self.finished: dict[int, ExecutionSlot] = {}
        self.entered: bool = False
        self.started_on: float = -1.0
        self._store: dict[str, Any] = {}
        self.alogger = logging.AdaptiveDebugLogger(logger.name)
        self.listeners: list[Callable[..., None]] = []

        self.enable_live_monitoring: bool = not config.get("debug") and sys.stdin.isatty()
        if os.getenv("CANARY_LEVEL") == "1":
            self.enable_live_monitoring = False
        elif os.getenv("CANARY_MAKE_DOCS"):
            self.enable_live_monitoring = False

    @property
    def inflight(self) -> dict[int, ExecutionSlot]:
        return self.submitted | self.running

    def add_listener(self, callback: Callable[..., None]) -> None:
        """Register a listener for job lifecycle events

        Listeners are called synchronously by the executor whenever a job transitions state.
        The listener signature must be::

            callback(event: str, *args: Any) -> None:

        Supported events and payloads are:

            ("job_submitted", ExectutionSlot)
            ("job_started", ExectutionSlot)
            ("job_finished", ExectutionSlot)

        """
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[..., None]) -> None:
        try:
            self.listeners.remove(callback)
        except ValueError:  # nosec B110
            pass

    def __enter__(self) -> "ResourceQueueExecutor":
        self._store.clear()
        try:
            # Since test cases run in subprocesses, we archive the config to the environment.  The
            # config object in the subprocess will read in the archive and use it to re-establish
            # the correct config
            self._start_mp_logging()
        except Exception:
            logger.exception("Unable to create configuration")
            raise
        self.entered = True
        self.started_on = time.time()
        return self

    def __exit__(self, *args):
        self.entered = False
        self.started_on = -1.0
        self._stop_mp_logging()

    def _start_mp_logging(self):
        self._store["logging_queue"] = logging_queue = mp.Queue(-1)
        root = logging.get_logger("root")
        handlers: list[logging.builtin_logging.Handler] = []
        handlers.append(logging.stream_handler())
        for h in root.handlers:
            if isinstance(h, logging.FileHandler) and isinstance(
                h.formatter, logging.JsonFormatter
            ):
                f = Path(h.baseFilename).absolute()
                handlers.append(logging.json_file_handler(f, h.level))
                self._store.setdefault("json_file_handlers", []).append(f)
        listener = logging.QueueListener(logging_queue, *handlers, respect_handler_level=True)
        listener.start()
        self._store["logging_listener"] = listener
        root.handlers.clear()
        root.addHandler(logging.QueueHandler(logging_queue))

    def _stop_mp_logging(self) -> None:
        listener: logging.QueueListener | None
        if listener := self._store.pop("logging_listener", None):
            listener.stop()
        logging.clear_handlers()
        logging.add_handler(logging.stream_handler())
        for file in self._store.pop("json_file_handlers", []):
            h = logging.json_file_handler(file)
            logging.add_handler(h)

    def run(self, **kwargs: Any) -> int:
        """Main loop: get jobs from queue and launch processes."""
        if not self.entered:
            raise RuntimeError(
                "ResourceQueueExecutor.run must be called in a ResourceQueueExector context"
            )

        logger.info(f"[bold]Starting[/] process pool with max {self.max_workers} workers")

        timeout = float(config.get("run:timeout:session", -1))
        qrank, qsize = 0, len(self.queue)
        start = time.time()
        logging_queue: mp.Queue = self._store["logging_queue"]
        config_snapshot = config.snapshot()
        reporter = LiveReporter(self) if self.enable_live_monitoring else EventReporter(self)
        with reporter:
            while True:
                try:
                    if timeout >= 0.0 and time.time() - start > timeout:
                        self._terminate_all(signal.SIGUSR2)
                        self._check_for_leaks()
                        raise TimeoutError(f"Test session exceeded time out of {timeout} s.")

                    # Clean up any finished processes and collect results
                    self._check_finished_processes()
                    self._check_for_leaks()

                    # Wait for a slot if at max capacity
                    self._wait_for_slot()

                    # Get a job from the queue
                    job = self.queue.get()
                    qrank += 1

                    # Create a result queue for this specific process
                    result_queue: mp.SimpleQueue = mp.SimpleQueue()

                    # Launch a new measured process
                    proc = mp.MeasuredProcess(
                        target=JobFunctor(),
                        args=(self.executor, job, result_queue, logging_queue, config_snapshot),
                        kwargs=kwargs,
                    )
                    proc.start()
                    pid: int = proc.pid  # type: ignore
                    self.submitted[pid] = ExecutionSlot(
                        proc=proc,
                        queue=result_queue,
                        job=job,
                        spawned=time.time(),
                        qrank=qrank,
                        qsize=qsize,
                    )

                except Busy:
                    # Queue is busy, wait and try again
                    time.sleep(self.busy_wait_time)

                except Empty:
                    # Queue is empty, wait for remaining jobs and exit
                    self._wait_all(start, timeout)
                    break

                except CanaryKill:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise StopExecution("canary.kill found", signal.SIGTERM)

                except KeyboardInterrupt:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise

                except TimeoutError:
                    raise

                except BaseException:
                    logger.exception("Unhandled exception in process pool")
                    raise
        return compute_returncode(self.queue.cases())

    def notify_listeners(self, event: EventTypes, *args: Any) -> None:
        for cb in self.listeners:
            cb(event, *args)

    def _check_timeouts(self) -> None:
        """Check for and kill processes that have exceeded their timeout."""
        now = time.time()
        timed_out: list[tuple[int, ExecutionSlot]] = []
        for pid, slot in list(self.inflight.items()):
            if not slot.proc.is_alive():
                continue
            if slot.started < 0:
                continue
            total_timeout = slot.job.timeout * self.timeout_multiplier
            if now - slot.started > total_timeout:
                timed_out.append((pid, slot))
        for pid, slot in timed_out:
            _ = self.running.pop(pid, None) or self.submitted.pop(pid)
            self.finished[pid] = slot
            total_timeout = slot.job.timeout * self.timeout_multiplier
            try:
                try:
                    measurements = slot.proc.get_measurements()
                except Exception:
                    measurements = {}
                try:
                    slot.proc.shutdown(signal.SIGTERM, grace_period=0.05)
                except Exception:
                    logger.exception(f"Failed shutting down timed-out process {pid}")
                try:
                    slot.job.refresh()
                    slot.job.timekeeper.update(
                        submitted=slot.submitted,
                        started=slot.started,
                        finished=now,
                    )
                    reason: str = f"Job timed out after {total_timeout} s."
                    if self.timeout_multiplier != 1.0:
                        reason += f" (={slot.job.timeout}*{self.timeout_multiplier})"
                    slot.job.set_status(status="TIMEOUT", reason=reason)
                    slot.job.measurements.update(measurements)
                    slot.job.save()
                except Exception:
                    logger.exception(f"Failed joining timed-out process {pid}")

            except Exception:
                logger.exception(f"Unexpected timeout finalization error for job {slot.job.id[:7]}")

            finally:
                logger.debug(
                    f"ResourceQueueExecutor._check_timeouts(): {slot.job=} timed out after "
                    f"{slot.job.timeout}*{self.timeout_multiplier}={total_timeout} s.",
                )
                self.queue.done(slot.job)
                self.notify_listeners("job_finished", slot)

    def _check_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self._check_timeouts()
        self._check_for_leaks()

        if Path("canary.kill").exists():
            Path("canary.kill").unlink()
            raise CanaryKill

        finished_pids: dict[int, Any] = {}
        for pid, slot in list(self.inflight.items()):
            while not slot.queue.empty():
                event = slot.queue.get()
                match event:
                    case ("SUBMITTED", ts):
                        slot.submitted = ts
                        self.notify_listeners("job_submitted", slot)
                    case ("STARTED", ts):
                        slot.started = ts
                        self.running[pid] = slot
                        self.submitted.pop(pid, None)
                        self.notify_listeners("job_started", slot)
                    case ("FINISHED", state):
                        slot.finished = time.time()
                        finished_pids[pid] = state
                    case _:
                        logger.warning(f"Unexpected event from submitted job {pid}: {event}")

        busy_pids: set[int] = set(self.inflight) - set(finished_pids)
        self.alogger.emit(
            tuple(sorted(busy_pids)),
            f"Finished pids: {list(finished_pids)}.  Busy pids: {list(busy_pids)}",
        )

        for pid, result in finished_pids.items():
            # Slot should be in either running or submitted (not both)
            slot = self.running.pop(pid, None) or self.submitted.pop(pid)
            assert pid not in self.running, "pid unexpectedly remains in running container"
            assert pid not in self.submitted, "pid unexpectedly remains in submitted container"
            self.finished[pid] = slot
            try:
                slot.job.setstate(result)
                measurements = slot.proc.get_measurements()
                slot.job.measurements.update(measurements)
                slot.job.save()
            except Exception:
                logger.exception(f"Post-processing failed for job {slot.job}")
                slot.job.set_status(status="ERROR", reason="Post-processing failure")
            finally:
                try:
                    slot.proc.join(timeout=0.01)  # Clean up the process
                except Exception:  # nosec B110
                    pass
                logger.debug(
                    f"ResourceQueueExecutor._check_finished_processes(): {slot.job=} finished "
                    f"with status {slot.job.status.status}"
                )
                self.queue.done(slot.job)
                self.notify_listeners("job_finished", slot)

    def _check_for_leaks(self) -> None:
        busy_ids = set(self.queue._busy)
        inflight_ids = {slot.job.id for slot in self.inflight.values()}
        if busy_ids != inflight_ids:
            leaked = busy_ids - inflight_ids
            missing = inflight_ids - busy_ids
            logger.critical(f"Busy/inflight mismatch leaked={leaked}, missing={missing}")
            raise StuckQueueError("Busy/inflight mismatch")
        terminal_busy = {job.id for job in self.queue._busy.values() if job.status.is_terminal()}
        if terminal_busy:
            logger.critical(f"Terminal jobs still marked busy: {','.join(terminal_busy)}")
            raise StuckQueueError(f"Terminal jobs still busy: {terminal_busy}")

    def _wait_for_slot(self) -> None:
        """Wait until a process slot is available."""
        while len(self.inflight) >= self.max_workers:
            self._check_finished_processes()
            self._check_for_leaks()
            if len(self.inflight) >= self.max_workers:
                time.sleep(0.05)  # Brief sleep before checking again

    def _wait_all(self, start: float, timeout: float) -> None:
        """Wait for all active processes to complete."""
        while True:
            if not self.inflight:
                break
            if timeout >= 0.0 and time.time() - start > timeout:
                self._terminate_all(signal.SIGUSR2)
                self._check_for_leaks()
                raise TimeoutError(f"Test session exceeded time out of {timeout} s.")
            else:
                self._check_finished_processes()
                self._check_for_leaks()
                time.sleep(0.075)

    def _terminate_all(self, signum: int):
        """Terminate all active processes."""
        inflight = list(self.inflight.items())
        self.running.clear()
        self.submitted.clear()
        for pid, slot in inflight:
            try:
                if slot.proc.is_alive():
                    try:
                        measurements = slot.proc.get_measurements()
                    except Exception:
                        measurements = {}
                    try:
                        slot.proc.shutdown(signum, grace_period=0.05)
                    except Exception:
                        logger.exception(f"Failed shutting down process {pid}")
                    slot.job.refresh()
                    stat = "CANCELLED" if signum == signal.SIGINT else "ERROR"
                    slot.job.set_status(status=stat, reason=f"Job terminated with signal {signum}")
                    slot.job.timekeeper.submitted = slot.submitted
                    slot.job.timekeeper.finished = time.time()
                    slot.job.measurements.update(measurements)
                    try:
                        slot.job.save()
                    except Exception:
                        logger.exception(f"Failed saving job {slot.job.id[:7]}")

                try:
                    slot.proc.join(timeout=0.1)
                except Exception:
                    logger.exception(f"Failed joining process {pid}")

            except Exception:
                logger.exception(f"Unexpected error terminating job {slot.job.id[:7]}")

            finally:
                logger.debug(f"ResourceQueueExecutor._terminate_all(): {slot.job=} terminated")
                self.queue.done(slot.job)
                self.notify_listeners("job_finished", slot)

        # Force kill if still alive
        for pid, slot in inflight:
            try:
                if slot.proc.is_alive():
                    logger.warning(f"Killing process {pid} (job {slot.job})")
                    slot.proc.kill()
            except Exception:
                logger.exception(f"Failed force-killing process {pid}")

        # Clean up
        for pid, slot in inflight:
            try:
                slot.proc.join(timeout=0.1)
            except Exception:  # nosec B110
                pass

        self.finished.update(inflight)
        self.queue.clear("CANCELLED" if signum == signal.SIGINT else "ERROR")

    @cached_property
    def timeout_multiplier(self) -> float:
        if cli_timeouts := config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                return float(t)
        elif t := config.get("run:timeout:multiplier"):
            return float(t)
        return 1.0


class LiveReporter:
    def __init__(self, executor: ResourceQueueExecutor) -> None:
        self.executor = executor
        console = Console(file=sys.stdout, force_terminal=True)
        self.live = Live(refresh_per_second=1, console=console, transient=False, auto_refresh=False)
        # Logging control
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

    def final_table(self) -> Group:
        xtor = self.executor
        text = xtor.queue.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
        table = Table(expand=False, box=box.SQUARE)
        fmt = config.getoption("live_name_fmt")
        table.add_column("Job")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Queued")
        table.add_column("Elapsed")
        table.add_column("Details")
        cases = xtor.queue.cases()
        for case in cases:
            if case.status.category == "PASS":
                continue
            queued = case.timekeeper.queued()
            elapsed = case.timekeeper.duration()
            table.add_row(
                case.display_name(style="rich", resolve=fmt == "long"),
                case.id[:7],
                case.status.display_name(style="rich"),
                f"{queued:5.1f}s",
                f"{elapsed:5.1f}s",
                case.status.reason or "",
            )
        if not table.row_count:
            n = len(cases)
            return Group(f"[blue]INFO[/]: {n}/{n} tests finished with status [bold green]PASS[/]")
        return Group(table, footer)

    def dynamic_table(self) -> Group:
        xtor = self.executor
        text = xtor.queue.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
        table = Table(expand=False, box=box.SQUARE)
        fmt = config.getoption("live_name_fmt")
        table = Table(expand=False, box=box.SQUARE)
        table.add_column("Job")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Queued")
        table.add_column("Elapsed")
        table.add_column("Rank")

        max_rows: int = 30
        num_inflight = len(xtor.inflight)
        if num_inflight < max_rows:
            n = max_rows - num_inflight
            for slot in sorted(xtor.finished.values(), key=lambda x: x.qrank)[-n:]:
                queued = slot.started - slot.spawned
                elapsed = slot.finished - slot.spawned
                table.add_row(
                    slot.job.display_name(style="rich", resolve=fmt == "long"),
                    slot.job.id[:7],
                    slot.job.status.display_name(style="rich"),
                    f"{queued:5.1f}s",
                    f"{elapsed:5.1f}s",
                    f"{slot.qrank}/{slot.qsize}",
                )

        now = time.time()
        for slot in sorted(xtor.running.values(), key=lambda x: x.qrank):
            queued = slot.started - slot.spawned
            elapsed = now - slot.spawned
            table.add_row(
                slot.job.display_name(style="rich", resolve=fmt == "long"),
                slot.job.id[:7],
                "[green]RUNNING[/]",
                f"{queued:5.1f}s",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        now = time.time()
        for slot in sorted(xtor.submitted.values(), key=lambda x: x.qrank):
            queued = elapsed = now - slot.spawned
            table.add_row(
                slot.job.display_name(style="rich", resolve=fmt == "long"),
                slot.job.id[:7],
                "[cyan]SUBMITTED[/]",
                f"{queued:5.1f}s",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        if table.row_count < max_rows:
            st = "[magenta]PENDING[/]"
            na = "NA"
            for job in xtor.queue.pending():
                table.add_row(
                    job.display_name(style="rich", resolve=fmt == "long"), job.id[:7], st, na, na
                )
                if table.row_count >= max_rows:
                    break

        if not table.row_count:
            return Group("")

        return Group(table, footer)


class EventReporter:
    def __init__(self, executor: ResourceQueueExecutor) -> None:
        self.executor = executor
        self.table = StaticTable()
        self.table.add_column("Job", 50)
        self.table.add_column("ID", 7)
        self.table.add_column("Status", 15)
        self.table.add_column("Queued", 7, "right")
        self.table.add_column("Elapsed", 7, "right")
        self.table.add_column("Rank", 8, "right")

    def __enter__(self):
        self.executor.add_listener(self.on_event)
        self.table.print_header_once()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.executor.remove_listener(self.on_event)

    def on_event(self, event: str, *args, **kwargs) -> None:
        match event:
            case "job_submitted":
                slot: ExecutionSlot = args[0]
                self.on_job_submit(slot)
            case "job_started":
                slot: ExecutionSlot = args[0]
                self.on_job_start(slot)
            case "job_finished":
                slot: ExecutionSlot = args[0]
                self.on_job_finish(slot)
            case _:
                pass

    def on_job_submit(self, slot: ExecutionSlot) -> None:
        fmt = config.getoption("live_name_fmt")
        row = [
            slot.job.display_name(style="rich", resolve=fmt == "long"),
            slot.job.id[:7],
            "[cyan]SUBMITTED[/]",
            "",
            "",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        rprint(text, file=sys.stderr)

    def on_job_start(self, slot: ExecutionSlot) -> None:
        now = time.time()
        queued = now - slot.spawned
        fmt = config.getoption("live_name_fmt")
        row = [
            slot.job.display_name(style="rich", resolve=fmt == "long"),
            slot.job.id[:7],
            "[blue]STARTED[/]",
            f"{queued:5.1f}s",
            "",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        rprint(text, file=sys.stderr)

    def on_job_finish(self, slot: ExecutionSlot) -> None:
        queued = slot.started - slot.spawned
        elapsed = slot.finished - slot.spawned
        fmt = config.getoption("live_name_fmt")
        row = [
            slot.job.display_name(style="rich", resolve=fmt == "long"),
            slot.job.id[:7],
            slot.job.status.display_name(style="rich"),
            f"{queued:5.1f}s",
            f"{elapsed:5.1f}s",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        rprint(text, file=sys.stderr)


@dataclasses.dataclass
class StaticColumn:
    header: str
    width: int
    align: Literal["left", "right"] = "left"


class StaticTable:
    def __init__(self, columns: list[StaticColumn] | None = None) -> None:
        self.columns = list(columns or [])
        self._printed_header = False

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

    def print_header_once(self):
        if not self._printed_header:
            text = self.render_header()
            rprint(text)
            rprint("─" * len(text))
            self._printed_header = True


class CanaryKill(Exception):
    pass


class StuckQueueError(Exception):
    pass
