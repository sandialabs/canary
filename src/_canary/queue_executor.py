# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import io
import math
import os
import signal
import sys
import time
from functools import cached_property
from pathlib import Path
from typing import Any
from typing import Callable
from typing import cast

from rich import print as rprint
from rich.console import Console
from rich.console import Group
from rich.live import Live
from rich.table import Table

from . import config
from .error import StopExecution
from .protocols import JobProtocol
from .queue import Busy
from .queue import Empty
from .queue import ResourceQueue
from .util import cpu_count
from .util import logging
from .util import multiprocessing as mp
from .util.misc import digits
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class ExecutionSlot:
    job: JobProtocol
    qrank: int
    qsize: int
    submit_time: float
    proc: mp.MeasuredProcess
    queue: mp.SimpleQueue
    start_time: float = -1.0


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
        self.event_sink: JobEventSink = NULL_SINK

        self.enable_live_monitoring: bool = not config.get("debug") and sys.stdin.isatty()
        if os.getenv("CANARY_LEVEL") == "1":
            self.enable_live_monitoring = False
        elif os.getenv("CANARY_MAKE_DOCS"):
            self.enable_live_monitoring = False

    @property
    def inflight(self) -> dict[int, ExecutionSlot]:
        return self.submitted | self.running

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

        renderer = ConsoleRenderer.factory(self._render_dashboard, self.enable_live_monitoring)
        with ConsoleReporter(renderer) as reporter:
            self.event_sink = cast(JobEventSink, reporter)
            while True:
                try:
                    if timeout >= 0.0 and time.time() - start > timeout:
                        self._terminate_all(signal.SIGUSR2)
                        self._check_for_leaks()
                        raise TimeoutError(f"Test session exceeded time out of {timeout} s.")

                    # Clean up any finished processes and collect results
                    self._check_finished_processes()
                    self._check_for_leaks()
                    reporter.update()

                    # Wait for a slot if at max capacity
                    self._wait_for_slot()
                    reporter.update()

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
                        submit_time=time.time(),
                        qrank=qrank,
                        qsize=qsize,
                    )
                    reporter.update()
                    self.event_sink.on_event("start", job, qrank, qsize)

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
                    reporter.update(final=True)
                    raise StopExecution("canary.kill found", signal.SIGTERM)

                except KeyboardInterrupt:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    reporter.update(final=True)
                    raise

                except TimeoutError:
                    reporter.update(final=True)
                    raise

                except BaseException:
                    logger.exception("Unhandled exception in process pool")
                    reporter.update(final=True)
                    raise

            self.event_sink = NULL_SINK
            reporter.update(final=True)
        return compute_returncode(self.queue.cases())

    def _check_timeouts(self) -> None:
        """Check for and kill processes that have exceeded their timeout."""
        now = time.time()
        timed_out: list[tuple[int, ExecutionSlot]] = []
        for pid, slot in list(self.inflight.items()):
            if not slot.proc.is_alive():
                continue
            total_timeout = slot.job.timeout * self.timeout_multiplier
            if now - slot.submit_time > total_timeout:
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
                        submitted_on=datetime.datetime.fromtimestamp(slot.submit_time).isoformat(),
                        started_on=datetime.datetime.fromtimestamp(slot.start_time).isoformat(),
                        finished_on=datetime.datetime.fromtimestamp(now).isoformat(),
                        duration=now - slot.start_time,
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
                self.event_sink.on_event("finish", slot.job, slot.qrank, slot.qsize)

    def _check_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self._check_timeouts()
        self._check_for_leaks()

        if Path("canary.kill").exists():
            Path("canary.kill").unlink()
            raise CanaryKill

        finished_pids: dict[int, Any] = {}
        for pid, slot in list(self.submitted.items()):
            if slot.queue.empty():
                continue
            event = slot.queue.get()
            match event:
                case ("STARTED", ts):
                    slot.start_time = ts
                    self.submitted.pop(pid)
                    self.running[pid] = slot
                case ("FINISHED", state):
                    finished_pids[pid] = state
                case _:
                    logger.warning(f"Unexpected event from submitted job {pid}: {event}")
        for pid, slot in list(self.running.items()):
            if slot.queue.empty():
                continue
            event = slot.queue.get()
            match event:
                case ("FINISHED", state):
                    finished_pids[pid] = state

        busy_pids: set[int] = set(self.inflight) - set(finished_pids)
        self.alogger.emit(
            tuple(sorted(busy_pids)),
            f"Finished pids: {list(finished_pids)}.  Busy pids: {list(busy_pids)}",
        )

        for pid, result in finished_pids.items():
            slot = self.running.pop(pid, None) or self.submitted.pop(pid)
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
                self.event_sink.on_event("finish", slot.job, slot.qrank, slot.qsize)

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
                self.event_sink.on_event("update")

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
                self.event_sink.on_event("finish", slot.job, slot.qrank, slot.qsize)

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

    def _render_dashboard(self, final: bool = False) -> Group | str:
        text = self.queue.status(start=self.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
        table = Table(expand=False)
        fmt = config.getoption("live_name_fmt")
        if final:
            table.add_column("Job")
            table.add_column("ID")
            table.add_column("Status")
            table.add_column("Elapsed")
            table.add_column("Details")
            cases = self.queue.cases()
            for case in cases:
                if case.status.category == "PASS":
                    continue
                elapsed = case.timekeeper.duration
                table.add_row(
                    case.display_name(style="rich", resolve=fmt == "long"),
                    case.id[:7],
                    case.status.display_name(style="rich"),
                    f"{elapsed:5.1f}s",
                    case.status.reason or "",
                )
            if not table.row_count:
                n = len(cases)
                return Group(
                    f"[blue]INFO[/]: {n}/{n} tests finished with status [bold green]PASS[/]"
                )
            return Group(table, footer)

        table = Table(expand=False)
        table.add_column("Job")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Elapsed")
        table.add_column("Rank")

        max_rows: int = 30
        num_inflight = len(self.inflight)
        if num_inflight < max_rows:
            n = max_rows - num_inflight
            for slot in sorted(self.finished.values(), key=lambda x: x.qrank)[-n:]:
                elapsed = slot.job.timekeeper.duration
                table.add_row(
                    slot.job.display_name(style="rich", resolve=fmt == "long"),
                    slot.job.id[:7],
                    slot.job.status.display_name(style="rich"),
                    f"{elapsed:5.1f}s",
                    f"{slot.qrank}/{slot.qsize}",
                )

        now = time.time()
        for slot in sorted(self.running.values(), key=lambda x: x.qrank):
            elapsed = now - slot.start_time
            table.add_row(
                slot.job.display_name(style="rich", resolve=fmt == "long"),
                slot.job.id[:7],
                "[green]RUNNING[/]",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        now = time.time()
        for slot in sorted(self.submitted.values(), key=lambda x: x.qrank):
            elapsed = now - slot.submit_time
            table.add_row(
                slot.job.display_name(style="rich", resolve=fmt == "long"),
                slot.job.id[:7],
                "[cyan]SUBMITTED[/]",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        if table.row_count < max_rows:
            st = "[magenta]PENDING[/]"
            na = "NA"
            for job in self.queue.pending():
                table.add_row(
                    job.display_name(style="rich", resolve=fmt == "long"), job.id[:7], st, na, na
                )
                if table.row_count >= max_rows:
                    break

        if not table.row_count:
            return Group("")

        return Group(table, footer)


class ConsoleReporter:
    def __init__(self, renderer: "ConsoleRenderer") -> None:
        self.renderer = renderer
        self.live: Live | None = None
        self.console: Console | None = None
        if self.renderer.live:
            self.console = Console(file=sys.stdout, force_terminal=True)

        # Logging control
        self._filter = logging.MuteConsoleFilter()
        self._stream_handlers: list[logging.builtin_logging.StreamHandler] = []
        self._mark: float = -1.0

    def __enter__(self):
        if self.renderer.live:
            self.mute_stream_handlers()
            self.live = Live(
                refresh_per_second=1,
                console=self.console,
                transient=False,
                auto_refresh=False,
            )
            self.live.__enter__()
        self._mark = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.live:
            self.live.__exit__(exc_type, exc, tb)
            self.unmute_stream_handlers()

    def update(self, final: bool = False) -> None:
        if self.live:
            if final or time.monotonic() - self._mark > 0.25:
                self.live.update(self.renderer.render(final=final) or "", refresh=True)
                self._mark = time.monotonic()
        elif final:
            group = self.renderer.render(final=True)
            rprint(group)

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

    def on_event(self, event: str, *args, **kwargs) -> None:
        if event == "start":
            self.renderer.on_job_start(*args)
        elif event == "finish":
            self.renderer.on_job_finish(*args)
        elif event == "update":
            self.update(**kwargs)


class JobEventSink:
    def on_event(self, evant: str, *args, **kwargs) -> None:
        pass


NULL_SINK = JobEventSink()


class ConsoleRenderer:
    live: bool = False

    def render(self, *, final: bool = False) -> Group | str:
        raise NotImplementedError

    @staticmethod
    def factory(render_fn: Callable[..., Group | str], live: bool) -> "ConsoleRenderer":
        if live:
            return LiveRenderer(render_fn)
        return StaticRenderer(render_fn)

    def on_job_start(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        pass

    def on_job_finish(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        pass


class LiveRenderer(ConsoleRenderer):
    live: bool = True

    def __init__(self, render_fn: Callable[..., Group | str]) -> None:
        self.render_fn = render_fn

    def render(self, *, final: bool = False) -> Group | str:
        return self.render_fn(final=final)


class StaticRenderer(ConsoleRenderer):
    def __init__(self, render_fn: Callable[..., Group | str]) -> None:
        self.render_fn = render_fn

    def render(self, *, final: bool = False) -> Group | str:
        if final:
            return self.render_fn(final=True)
        return ""

    def on_job_start(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        fmt = io.StringIO()
        fmt.write(datetime.datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
        fmt.write(r"[bold]\[%s][/] " % f"{qrank:0{digits(qsize)}}/{qsize}")
        fmt.write("[bold]Starting[/] job %s: %s" % (job.id[:7], job.display_name()))
        logger.log(logging.EMIT, fmt.getvalue().strip(), extra={"prefix": ""})

    def on_job_finish(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        try:
            fmt = io.StringIO()
            fmt.write(datetime.datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            fmt.write(r"[bold]\[%s][/] " % f"{qrank:0{digits(qsize)}}/{qsize}")
            fmt.write(
                "[bold]Finished[/] job %s: %s: %s"
                % (job.id[:7], job.display_name(), job.status.display_name())
            )
            logger.log(logging.EMIT, fmt.getvalue().strip(), extra={"prefix": ""})
        except Exception:
            logger.exception(f"Failed logging finished state of {job.id[:7]}")
        for h in logger.handlers:
            h.flush()


class CanaryKill(Exception):
    pass


class StuckQueueError(Exception):
    pass
