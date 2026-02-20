# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import math
import os
import shutil
import signal
import sys
import threading
import time
from functools import cached_property
from pathlib import Path
from queue import Empty as QueueEmpty
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
from .util.misc import boolean
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)

EventTypes = Literal["job_submitted", "job_started", "job_finished"]


@dataclasses.dataclass
class ExecutionSlot:
    job: JobProtocol
    qrank: int
    qsize: int
    spawned: float
    worker_id: int
    submitted: float = -1.0
    started: float = -1.0
    finished: float = -1.0


class JobFunctor:
    def __call__(
        self,
        executor: Callable,
        job: JobProtocol,
        result_queue: mp.Queue,
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
            job.set_status(status="ERROR", reason=repr(e))
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
                h.close()


def inner_ctx() -> Any:
    """
    Inner job process context.

    Default: fork (fast for many tiny tests).

    Override (env var):
      CANARY_INNER_START_METHOD=default|inherit -> use mp.get_context() (global default)
      CANARY_INNER_START_METHOD=spawn          -> force spawn
      CANARY_INNER_START_METHOD=forkserver     -> force forkserver
      CANARY_INNER_START_METHOD=fork           -> force fork
      CANARY_INNER_START_METHOD=auto           -> same as unset (defaults to fork)
    """
    override = os.getenv("CANARY_INNER_START_METHOD", "").strip().lower()

    if override in ("", "auto"):
        method = "fork"
    elif override in ("default", "inherit"):
        return mp.get_context()
    elif override in ("fork", "spawn", "forkserver"):
        method = override
    else:
        logger.warning(f"Unknown CANARY_INNER_START_METHOD={override!r}; falling back to fork")
        method = "fork"

    try:
        return mp.get_context(method)  # type: ignore[arg-type]
    except Exception as e:
        logger.warning(f"inner_ctx: failed to get_context({method!r}): {e}; using default")
        return mp.get_context()


def worker_main(
    worker_id: int,
    task_q: mp.Queue,
    event_q: mp.Queue,
    logging_queue: mp.Queue,
    config_snapshot: dict[str, Any],
    timeout_multiplier: float,
    executor: Callable,
    common_kwargs: dict[str, Any],
) -> None:
    """
    Long-lived worker process. For each job, spawn an inner measured process to keep per-job
    measurements and strong isolation.

    Notes:
      - `local_q` MUST support timeout/nonblocking operations so we can enforce timeouts even when
        the child stops emitting events.
      - We call proc.is_alive() periodically even when events are flowing to sample metrics.
    """
    config.load_snapshot(config_snapshot)
    ctx = inner_ctx()

    # Sampling / polling controls
    poll_sleep = 0.01
    metric_sample_period = 0.10  # seconds
    last_sample = 0.0

    while True:
        msg = task_q.get()
        if msg is None:
            return

        job, per_job_kwargs = msg
        job_id = job.id

        # IMPORTANT: use mp.Queue (not SimpleQueue) so we can do get(timeout=...)
        local_q: mp.Queue = mp.Queue()
        proc = mp.MeasuredProcess(
            ctx=ctx,
            target=JobFunctor(),
            args=(executor, job, local_q, logging_queue, config_snapshot),
            kwargs={**common_kwargs, **(per_job_kwargs or {})},
        )
        proc.start()

        t0 = time.time()
        hard_deadline = t0 + job.timeout * timeout_multiplier

        while True:
            # Periodic metric sampling independent of events
            now = time.time()
            if now - last_sample >= metric_sample_period:
                try:
                    _ = proc.is_alive()  # samples metrics in MeasuredProcess wrapper
                except Exception:  # nosec B110
                    pass
                last_sample = now

            # Try to read one event with a short timeout
            try:
                tag, payload = local_q.get(timeout=0.05)
            except QueueEmpty:
                tag = None
                payload = None

            if tag == "SUBMITTED":
                event_q.put((job_id, "SUBMITTED", float(payload), worker_id))
                continue

            if tag == "STARTED":
                event_q.put((job_id, "STARTED", float(payload), worker_id))
                continue

            if tag == "FINISHED":
                state = payload
                measurements = proc.get_measurements()
                event_q.put((job_id, "FINISHED", state, measurements, worker_id))
                break

            if tag is not None:
                event_q.put((job_id, "WARN", (tag, payload), worker_id))
                continue

            # No event this tick: enforce timeout / detect death
            if proc.is_alive() and time.time() > hard_deadline:
                try:
                    measurements = proc.get_measurements()
                except Exception:
                    measurements = {}
                try:
                    proc.shutdown(signal.SIGTERM, grace_period=0.05)
                except Exception:  # nosec B110
                    pass
                event_q.put((job_id, "TIMEOUT", measurements, worker_id))
                break

            if not proc.is_alive():
                # Process exited but FINISHED was never observed
                try:
                    measurements = proc.get_measurements()
                except Exception:
                    measurements = {}
                event_q.put((job_id, "DIED", measurements, worker_id))
                break

            time.sleep(poll_sleep)

        try:
            local_q.close()
        except Exception:  # nosec B110
            pass
        try:
            proc.join(timeout=0.1)
            proc.close()
        except Exception:  # nosec B110
            pass


class ResourceQueueExecutor:
    """Manages a pool of worker processes with timeout support and metrics collection."""

    def __init__(
        self,
        queue: ResourceQueue,
        executor: Callable,
        max_workers: int = -1,
        busy_wait_time: float = 0.05,
    ):
        nproc = cpu_count()
        self.max_workers = max_workers if max_workers > 0 else math.ceil(0.85 * nproc)
        if self.max_workers > nproc:
            logger.warning(f"workers={self.max_workers} > cpu_count={nproc}")

        self.queue: ResourceQueue = queue
        self.executor = executor
        self.busy_wait_time = busy_wait_time

        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}
        self.entered: bool = False
        self.started_on: float = -1.0
        self._store: dict[str, Any] = {}
        self.alogger = logging.AdaptiveDebugLogger(logger.name)
        self.listeners: list[Callable[..., None]] = []

        # worker infrastructure
        self.workers: list[dict[str, Any]] = []
        self.idle_workers: list[int] = []
        self.busy_workers: dict[int, str] = {}  # worker_id -> job_id
        self.event_q: mp.Queue | None = None
        self.slots_by_id: dict[str, ExecutionSlot] = {}

        style = config.getoption("console_style") or {}
        self.live_reporting = style.get("live", True)
        if config.get("debug"):
            self.live_reporting = False
        if not sys.stdin.isatty():
            self.live_reporting = False
        if "CANARY_LIVE" in os.environ and not boolean(os.environ["CANARY_LIVE"]):
            self.live_reporting = False
        elif int(os.getenv("CANARY_LEVEL", "0")) > 0:
            self.live_reporting = False
        elif os.getenv("CANARY_MAKE_DOCS"):
            self.live_reporting = False

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    def add_listener(self, callback: Callable[..., None]) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[..., None]) -> None:
        try:
            self.listeners.remove(callback)
        except ValueError:  # nosec B110
            pass

    def __enter__(self) -> "ResourceQueueExecutor":
        self._store.clear()
        self._start_mp_logging()

        self.event_q = mp.Queue(-1)
        logging_queue: mp.Queue = self._store["logging_queue"]
        config_snapshot = config.snapshot()

        common_kwargs: dict[str, Any] = {}

        # Start persistent workers once (use global default context)
        ctx = mp.get_context()
        for wid in range(self.max_workers):
            task_q = mp.Queue(-1)
            proc = ctx.Process(  # type: ignore
                target=worker_main,
                args=(
                    wid,
                    task_q,
                    self.event_q,
                    logging_queue,
                    config_snapshot,
                    self.timeout_multiplier,
                    self.executor,
                    common_kwargs,
                ),
                kwargs={},
            )
            proc.start()
            self.workers.append({"id": wid, "task_q": task_q, "proc": proc})
            self.idle_workers.append(wid)

        self.entered = True
        self.started_on = time.time()
        return self

    def __exit__(self, *args):
        self.entered = False
        self.started_on = -1.0
        self._shutdown_workers()
        self._stop_mp_logging()

    def _shutdown_workers(self) -> None:
        for w in self.workers:
            try:
                w["task_q"].put(None)
            except Exception:  # nosec B110
                pass
        for w in self.workers:
            try:
                w["proc"].join(timeout=0.2)
                w["proc"].close()
            except Exception:  # nosec B110
                pass
        self.workers.clear()
        self.idle_workers.clear()
        self.busy_workers.clear()

    def _start_mp_logging(self) -> None:
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
        if listener := self._store.pop("logging_listener", None):
            listener.stop()
        logging.clear_handlers()
        logging.add_handler(logging.stream_handler())
        for file in self._store.pop("json_file_handlers", []):
            h = logging.json_file_handler(file)
            logging.add_handler(h)
        if logging_queue := self._store.pop("logging_queue", None):
            logging_queue.close()
            logging_queue.join_thread()

    def run(self, **kwargs: Any) -> int:
        if not self.entered:
            raise RuntimeError("ResourceQueueExecutor.run must be called in a context")

        logger.info(f"[bold]Starting[/] process pool with max {self.max_workers} workers")

        session_timeout = float(config.get("run:timeout:session", -1))
        qrank, qsize = 0, len(self.queue)
        start = time.time()

        reporter = LiveReporter(self) if self.live_reporting else EventReporter(self)
        with reporter:
            while True:
                try:
                    if session_timeout >= 0.0 and time.time() - start > session_timeout:
                        self._terminate_all(signal.SIGUSR2)
                        self._check_for_leaks()
                        raise TimeoutError(
                            f"Test session exceeded time out of {session_timeout} s."
                        )

                    self._check_finished_processes()
                    self._check_for_leaks()

                    # Wait for an idle worker
                    while not self.idle_workers:
                        self._check_finished_processes()
                        self._check_for_leaks()
                        if session_timeout >= 0.0 and time.time() - start > session_timeout:
                            self._terminate_all(signal.SIGUSR2)
                            self._check_for_leaks()
                            raise TimeoutError(
                                f"Test session exceeded time out of {session_timeout} s."
                            )
                        time.sleep(0.01)

                    job = self.queue.get()
                    qrank += 1

                    wid = self.idle_workers.pop()
                    self.busy_workers[wid] = job.id
                    slot = ExecutionSlot(
                        job=job,
                        spawned=time.time(),
                        qrank=qrank,
                        qsize=qsize,
                        worker_id=wid,
                    )
                    self.slots_by_id[job.id] = slot
                    self.submitted[job.id] = slot

                    self.workers[wid]["task_q"].put((job, kwargs))

                except Busy:
                    time.sleep(self.busy_wait_time)

                except Empty:
                    self._wait_all(start, session_timeout)
                    break

                except CanaryKill:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise StopExecution("canary.kill found", signal.SIGTERM)

                except KeyboardInterrupt:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks()
                    raise

        return compute_returncode(self.queue.cases())

    def notify_listeners(self, event: EventTypes, *args: Any) -> None:
        for cb in self.listeners:
            cb(event, *args)

    def _check_finished_processes(self) -> None:
        self._check_for_leaks()

        if Path("canary.kill").exists():
            Path("canary.kill").unlink()
            raise CanaryKill

        assert self.event_q is not None

        while True:
            try:
                job_id, tag, *rest = self.event_q.get_nowait()
            except QueueEmpty:
                break

            slot = self.slots_by_id.get(job_id)
            if slot is None:
                continue

            if tag == "SUBMITTED":
                ts, _wid = rest
                slot.submitted = float(ts)
                self.notify_listeners("job_submitted", slot)
                continue

            if tag == "STARTED":
                ts, _wid = rest
                slot.started = float(ts)
                self.running[job_id] = slot
                self.submitted.pop(job_id, None)
                self.notify_listeners("job_started", slot)
                continue

            if tag == "FINISHED":
                state, measurements, wid = rest
                slot.finished = time.time()
                try:
                    slot.job.setstate(state)
                    slot.job.measurements.update(measurements)
                    slot.job.save()
                except Exception:
                    logger.exception(f"Post-processing failed for job {slot.job}")
                    slot.job.set_status(status="ERROR", reason="Post-processing failure")
                    try:
                        slot.job.save()
                    except Exception:  # nosec B110
                        pass
                finally:
                    self.finished[job_id] = slot
                    self.running.pop(job_id, None)
                    self.submitted.pop(job_id, None)
                    self.queue.done(slot.job)
                    self.notify_listeners("job_finished", slot)
                    self.busy_workers.pop(int(wid), None)
                    self.idle_workers.append(int(wid))
                continue

            if tag == "TIMEOUT":
                measurements, wid = rest
                slot.finished = time.time()
                total_timeout = slot.job.timeout * self.timeout_multiplier
                slot.job.set_status(
                    status="TIMEOUT",
                    reason=f"Job timed out after {total_timeout} s.",
                )
                slot.job.measurements.update(measurements)
                slot.job.save()

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.queue.done(slot.job)
                self.notify_listeners("job_finished", slot)
                self.busy_workers.pop(int(wid), None)
                self.idle_workers.append(int(wid))
                continue

            if tag == "DIED":
                measurements, wid = rest
                slot.finished = time.time()
                slot.job.set_status(status="ERROR", reason="Worker job process died unexpectedly")
                slot.job.measurements.update(measurements)
                slot.job.save()

                self.finished[job_id] = slot
                self.running.pop(job_id, None)
                self.submitted.pop(job_id, None)
                self.queue.done(slot.job)
                self.notify_listeners("job_finished", slot)
                self.busy_workers.pop(int(wid), None)
                self.idle_workers.append(int(wid))
                continue

            logger.warning(f"Unexpected worker event for {job_id[:7]}: {tag} {rest}")

    def _check_for_leaks(self) -> None:
        # NOTE: still reads queue internals; ideally ResourceQueue should provide a safe accessor.
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

    def _wait_all(self, start: float, timeout: float) -> None:
        while True:
            if not self.inflight:
                break
            if timeout >= 0.0 and time.time() - start > timeout:
                self._terminate_all(signal.SIGUSR2)
                self._check_for_leaks()
                raise TimeoutError(f"Test session exceeded time out of {timeout} s.")
            self._check_finished_processes()
            self._check_for_leaks()
            time.sleep(0.05)

    def _terminate_all(self, signum: int) -> None:
        stat = "CANCELLED" if signum == signal.SIGINT else "ERROR"
        reason = f"Job terminated with signal {signum}"

        inflight_slots = list(self.inflight.values())
        self.running.clear()
        self.submitted.clear()

        for slot in inflight_slots:
            try:
                slot.job.refresh()
            except Exception:  # nosec B110
                pass
            try:
                slot.job.set_status(status=stat, reason=reason)
                slot.job.timekeeper.submitted = slot.submitted
                slot.job.timekeeper.finished = time.time()
                slot.finished = time.time()
                slot.job.save()
            except Exception:
                logger.exception(f"Unexpected error terminating job {slot.job.id[:7]}")
            finally:
                self.finished[slot.job.id] = slot
                try:
                    self.queue.done(slot.job)
                except Exception:  # nosec B110
                    pass
                self.notify_listeners("job_finished", slot)

        self._shutdown_workers()
        self.queue.clear(stat)

    @cached_property
    def timeout_multiplier(self) -> float:
        if cli_timeouts := config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                return float(t)
        elif t := config.get("run:timeout:multiplier"):
            return float(t)
        return 1.0


class Reporter:
    def __init__(self, executor: ResourceQueueExecutor) -> None:
        self.executor = executor
        style = config.getoption("console_style") or {}
        self.namefmt = style.get("name", "short")

    def final_table(self) -> Group:
        xtor = self.executor
        text = xtor.queue.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
        table = Table(expand=False, box=box.SQUARE)
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
                case.display_name(style="rich", resolve=self.namefmt == "long"),
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


class LiveReporter(Reporter):
    def __init__(self, executor: ResourceQueueExecutor) -> None:
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
        text = xtor.queue.status(start=xtor.started_on)
        footer = Table(expand=True, show_header=False, box=None)
        footer.add_column("stats")
        footer.add_row(text)
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
                    slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
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
                slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
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
                slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
                slot.job.id[:7],
                "[cyan]SUBMITTED[/]",
                f"{queued:5.1f}s",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        if table.row_count < max_rows:
            for job in xtor.queue.pending():
                table.add_row(
                    job.display_name(style="rich", resolve=self.namefmt == "long"),
                    job.id[:7],
                    "[magenta]PENDING[/]",
                    "NA",
                    "NA",
                )
                if table.row_count >= max_rows:
                    break

        if not table.row_count:
            return Group("")

        return Group(table, footer)


class EventReporter(Reporter):
    def __init__(self, executor: ResourceQueueExecutor) -> None:
        super().__init__(executor)
        self.table = StaticTable()
        maxnamelen: int = -1
        for s in executor.queue._heap:
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
        self.table.add_column("Job", maxnamelen)
        self.table.add_column("ID", n)
        self.table.add_column("Status", status_width)
        self.table.add_column("Queued", n, "right")
        self.table.add_column("Elapsed", n, "right")
        self.table.add_column("Rank", n, "right")

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
            "",
            "",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_start(self, slot: ExecutionSlot) -> None:
        now = time.time()
        queued = now - slot.spawned
        row = [
            slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
            slot.job.id[:7],
            "[blue]STARTED[/]",
            f"{queued:5.1f}s",
            "",
            f"{slot.qrank}/{slot.qsize}",
        ]
        text = self.table.render_row(row)
        logger.info(text.markup, extra={"prefix": ""})

    def on_job_finish(self, slot: ExecutionSlot) -> None:
        queued = slot.started - slot.spawned
        elapsed = slot.finished - slot.spawned
        row = [
            slot.job.display_name(style="rich", resolve=self.namefmt == "long"),
            slot.job.id[:7],
            slot.job.status.display_name(style="rich"),
            f"{queued:5.1f}s",
            f"{elapsed:5.1f}s",
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


class CanaryKill(Exception):
    pass


class StuckQueueError(Exception):
    pass
