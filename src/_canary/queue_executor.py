# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import io
import math
import multiprocessing as mp
import os
import signal
import sys
import time
import traceback
from functools import cached_property
from pathlib import Path
from queue import Empty as EmptyResultQueue
from typing import Any
from typing import Callable
from uuid import uuid4

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
from .util.misc import digits
from .util.procutils import MeasuredProcess
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)


@dataclasses.dataclass
class ExecutionSlot:
    job: JobProtocol
    qrank: int
    qsize: int
    start_time: float
    proc: MeasuredProcess
    queue: mp.Queue


def with_traceback(executor: Callable, job: JobProtocol, queue: mp.Queue, **kwargs: Any) -> None:
    try:
        return executor(job, queue, **kwargs)
    except Exception as e:  # nosec B110
        fh = io.StringIO()
        traceback.print_exc(file=fh)
        text = fh.getvalue()
        logger.debug(f"Child process failed: {text}")
        job.set_status(status="ERROR", reason=f"{e.__class__.__name__}({e.args[0]})")
        while not queue.empty():
            queue.get_nowait()
        queue.put({"status": job.status})
        sys.exit(1)


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

        self.inflight: dict[int, ExecutionSlot] = {}
        self.finished: dict[int, ExecutionSlot] = {}
        self.entered: bool = False
        self.started_on: float = -1.0

        self.enable_live_monitoring: bool = not config.get("debug") and sys.stdin.isatty()
        if os.getenv("CANARY_LEVEL") == "1":
            self.enable_live_monitoring = False

    def __enter__(self) -> "ResourceQueueExecutor":
        from .workspace import Workspace

        try:
            # Since test cases run in subprocesses, we archive the config to the environment.  The
            # config object in the subprocess will read in the archive and use it to re-establish
            # the correct config
            ws = Workspace.load()
            f = ws.tmp_dir / f"config/{uuid4().hex[:8]}.json"
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(f, "w") as fh:
                config.dump(fh)
            os.environ[config.CONFIG_ENV_FILENAME] = str(f)
        except Exception:
            logger.exception("Unable to create configuration")
            raise
        self.entered = True
        self.started_on = time.time()
        return self

    def __exit__(self, *args):
        self.entered = False
        self.started_on = -1.0

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

        with CanaryLive(self._render_dashboard, enable=self.enable_live_monitoring) as live:
            while True:
                try:
                    if timeout >= 0.0 and time.time() - start > timeout:
                        self._terminate_all(signal.SIGUSR2)
                        self._check_for_leaks(where="_terminate_all")
                        raise TimeoutError(f"Test session exceeded time out of {timeout} s.")

                    # Clean up any finished processes and collect results
                    self._check_finished_processes()
                    self._check_for_leaks(where="_check_finished_processes")
                    live.update()

                    # Wait for a slot if at max capacity
                    self._wait_for_slot()
                    live.update()

                    # Get a job from the queue
                    job = self.queue.get()
                    qrank += 1

                    # Create a result queue for this specific process
                    result_queue: mp.Queue = mp.Queue()

                    # Launch a new measured process
                    proc = MeasuredProcess(
                        target=with_traceback,
                        args=(self.executor, job, result_queue),
                        kwargs=kwargs,
                    )
                    proc.start()
                    pid: int = proc.pid  # type: ignore
                    self.inflight[pid] = ExecutionSlot(
                        proc=proc,
                        queue=result_queue,
                        job=job,
                        start_time=time.time(),
                        qrank=qrank,
                        qsize=qsize,
                    )
                    live.update()
                    self.on_job_start(job, qrank, qsize)

                except Busy:
                    # Queue is busy, wait and try again
                    time.sleep(self.busy_wait_time)

                except Empty:
                    # Queue is empty, wait for remaining jobs and exit
                    self._wait_all(live)
                    live.update(final=True)
                    break

                except CanaryKill:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks(where="_terminate_all")
                    live.update(final=True)
                    raise StopExecution("canary.kill found", signal.SIGTERM)

                except KeyboardInterrupt:
                    self._terminate_all(signal.SIGINT)
                    self._check_for_leaks(where="_terminate_all")
                    live.update(final=True)
                    raise

                except TimeoutError:
                    live.update(final=True)
                    raise

                except BaseException:
                    logger.exception("Unhandled exception in process pool")
                    live.update(final=True)
                    raise

            live.update(final=True)
        return compute_returncode(self.queue.cases())

    def on_job_start(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        if self.enable_live_monitoring:
            return
        fmt = io.StringIO()
        fmt.write(datetime.datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
        fmt.write(r"[bold]\[%s][/] " % f"{qrank:0{digits(qsize)}}/{qsize}")
        fmt.write("[bold]Starting[/] job %s: %s" % (job.id[:7], job.display_name()))
        logger.log(logging.EMIT, fmt.getvalue().strip(), extra={"prefix": ""})

    def on_job_finish(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        if self.enable_live_monitoring:
            return
        fmt = io.StringIO()
        fmt.write(datetime.datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
        fmt.write(r"[bold]\[%s][/] " % f"{qrank:0{digits(qsize)}}/{qsize}")
        fmt.write(
            "[bold]Finished[/] job %s: %s: %s"
            % (job.id[:7], job.display_name(), job.status.display_name())
        )
        logger.log(logging.EMIT, fmt.getvalue().strip(), extra={"prefix": ""})

    def _check_timeouts(self) -> None:
        """Check for and kill processes that have exceeded their timeout."""
        now = time.time()
        timed_out: list[tuple[int, ExecutionSlot]] = []
        for pid, slot in list(self.inflight.items()):
            if not slot.proc.is_alive():
                continue
            total_timeout = slot.job.timeout * self.timeout_multiplier
            if now - slot.start_time > total_timeout:
                timed_out.append((pid, slot))
        for pid, slot in timed_out:
            self.inflight.pop(pid, None)
            self.finished[pid] = slot
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
                    slot.job.set_status(
                        status="TIMEOUT",
                        reason=f"Job timed out after {slot.job.timeout}*{self.timeout_multiplier}={total_timeout} s.",
                    )
                    slot.job.measurements.update(measurements)
                    slot.job.save()
                except Exception:
                    logger.exception(f"Failed joining timed-out process {pid}")
            except Exception:
                logger.exception(f"Unexpected timeout finalization error for job {slot.job.id[:7]}")
            finally:
                self.queue.done(slot.job)
                self.on_job_finish(slot.job, slot.qrank, slot.qsize)

    def _check_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self._check_timeouts()
        self._check_for_leaks(where="_check_timeouts")

        if Path("canary.kill").exists():
            Path("canary.kill").unlink()
            raise CanaryKill

        finished_pids = [pid for pid, slot in self.inflight.items() if not slot.proc.is_alive()]

        for pid in finished_pids:
            slot = self.inflight.pop(pid)
            self.finished[pid] = slot
            try:
                # Get the final result before cleaning up
                try:
                    result = slot.queue.get_nowait()
                except (EmptyResultQueue, OSError):
                    slot.job.set_status(
                        status="ERROR", reason=f"No result found for job {slot.job} (pid {pid})"
                    )
                else:
                    slot.job.on_result(result)

                # Get measurements and store in job
                measurements = slot.proc.get_measurements()
                slot.job.measurements.update(measurements)
                slot.job.save()
            except Exception:
                logger.exception(f"Post-processing failed for job {slot.job}")
                slot.job.set_status(status="ERROR", reason="Post-processing failure")
            finally:
                try:
                    slot.queue.close()
                    slot.queue.join_thread()
                except Exception:  # nosec B110
                    pass

                try:
                    slot.proc.join()  # Clean up the process
                except Exception:  # nosec B110
                    pass

                self.queue.done(slot.job)
                self.on_job_finish(slot.job, slot.qrank, slot.qsize)

    def _check_for_leaks(self, *, where: str) -> None:
        leaked = set(self.queue._busy) - {slot.job.id for slot in self.inflight.values()}
        if leaked:
            logger.critical(f"Leaked busy jobs detected {','.join(leaked)} at {where}")

    def _wait_for_slot(self) -> None:
        """Wait until a process slot is available."""
        while len(self.inflight) >= self.max_workers:
            self._check_finished_processes()
            self._check_for_leaks(where="_check_finished_processes")
            if len(self.inflight) >= self.max_workers:
                time.sleep(0.05)  # Brief sleep before checking again

    def _wait_all(self, live: "CanaryLive") -> None:
        """Wait for all active processes to complete."""
        while self.inflight:
            self._check_finished_processes()
            self._check_for_leaks(where="_check_finished_processes")
            if self.inflight:
                time.sleep(0.075)
            live.update()

    def _terminate_all(self, signum: int):
        """Terminate all active processes."""
        inflight = list(self.inflight.items())
        self.inflight.clear()
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
                self.queue.done(slot.job)
                self.on_job_finish(slot.job, slot.qrank, slot.qsize)

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
            table.add_column("Duration")
            table.add_column("Details")
            for slot in sorted(self.finished.values(), key=lambda x: x.qrank):
                if slot.job.status.category == "PASS":
                    continue
                elapsed = slot.job.timekeeper.duration
                table.add_row(
                    slot.job.display_name(style="rich", resolve=fmt == "long"),
                    slot.job.id[:7],
                    slot.job.status.display_name(style="rich"),
                    f"{elapsed:5.1f}s",
                    slot.job.status.reason or "",
                )
            if not table.row_count:
                n = len(self.finished)
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
        for slot in sorted(self.inflight.values(), key=lambda x: x.qrank):
            elapsed = now - slot.start_time
            table.add_row(
                slot.job.display_name(style="rich", resolve=fmt == "long"),
                slot.job.id[:7],
                "[green]RUNNING[/green]",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        return Group(table, footer)


class CanaryLive:
    def __init__(self, factory: Callable[..., Group | str], *, enable: bool = True) -> None:
        self.factory = factory
        self.enabled = enable
        self.live: Live | None = None
        self.console: Console | None = None
        if self.enabled:
            self.console = Console(file=sys.stdout, force_terminal=True)

        # Logging control
        self._filter = logging.MuteConsoleFilter()
        self._stream_handlers: list[logging.builtin_logging.StreamHandler] = []
        self._mark: float = -1.0

    def __enter__(self):
        if self.enabled:
            self.mute_stream_handlers()
            self.live = Live(
                self.factory(),
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
                self.live.update(self.factory(final=final) or "", refresh=True)
                self._mark = time.monotonic()

    def mute_stream_handlers(self) -> None:
        root = logging.builtin_logging.getLogger(logging.root_log_name)
        for h in root.handlers:
            if isinstance(h, logging.builtin_logging.StreamHandler):
                h.addFilter(self._filter)
                self._stream_handlers.append(h)
        root = logging.builtin_logging.getLogger()
        for h in root.handlers:
            if isinstance(h, logging.builtin_logging.StreamHandler):
                h.addFilter(self._filter)
                self._stream_handlers.append(h)

    def unmute_stream_handlers(self) -> None:
        for h in self._stream_handlers:
            h.removeFilter(self._filter)
        self._stream_handlers.clear()


class CanaryKill(Exception):
    pass
