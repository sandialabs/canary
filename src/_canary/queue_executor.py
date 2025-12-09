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
from functools import cached_property
from pathlib import Path
from queue import Empty as EmptyResultQueue
from typing import Any
from typing import Callable
from uuid import uuid4

from rich.console import Console
from rich.live import Live
from rich.table import Table

from . import config
from .protocols import JobProtocol
from .queue import Busy
from .queue import Empty
from .queue import ResourceQueue
from .util import cpu_count
from .util import keyboard
from .util import logging
from .util.misc import digits
from .util.procutils import MeasuredProcess
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)

import traceback


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
        job.set_status("ERROR", reason=f"{e.__class__.__name__}({e.args[0]})")
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

    def __enter__(self) -> "ResourceQueueExecutor":
        from .workspace import Workspace

        try:
            # Since test cases run in subprocesses, we archive the config to the environment.  The
            # config object in the subprocess will read in the archive and use it to re-establish
            # the correct config
            ws = Workspace.load()
            f = ws.tmp_dir / f"{uuid4().hex[:8]}.json"
            with open(f, "w") as fh:
                config.dump(fh)
            os.environ[config.CONFIG_ENV_FILENAME] = str(f)
        except Exception:
            logger.exception("Unable to create configuration")
            raise
        self.entered = True
        return self

    def __exit__(self, *args):
        if f := os.getenv(config.CONFIG_ENV_FILENAME):
            Path(f).unlink(missing_ok=True)
        self.entered = False

    def run(self, **kwargs: Any) -> int:
        """Main loop: get jobs from queue and launch processes."""
        if not self.entered:
            raise RuntimeError(
                "ResourceQueueExecutor.run must be called in a ResourceQueueExector context"
            )

        logger.info(f"@*{{Starting}} process pool with max {self.max_workers} workers")

        timeout = float(config.get("timeout:session", -1))
        qrank, qsize = 0, len(self.queue)
        start = time.time()

        console: Console | None = None
        if not config.get("debug") and sys.stdin.isatty():
            console = Console()
        with CanaryLive(self._render_dashboard, console=console) as live:
            while True:
                try:
                    if timeout >= 0.0 and time.time() - start > timeout:
                        self._terminate_all(signal.SIGUSR2)
                        raise TimeoutError(f"Test session exceeded time out of {timeout} s.")

                    self._check_keyboard_input(start)

                    # Clean up any finished processes and collect results
                    self._check_finished_processes()
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
                    self.on_job_start(job, qrank, qsize)
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

                except Busy:
                    # Queue is busy, wait and try again
                    time.sleep(self.busy_wait_time)

                except Empty:
                    # Queue is empty, wait for remaining jobs and exit
                    self._wait_all(live)
                    break

                except KeyboardInterrupt:
                    self._terminate_all(signal.SIGINT)
                    raise

                except TimeoutError:
                    raise

                except BaseException:
                    logger.exception("Unhandled exception in process pool")
                    raise
                finally:
                    live.update()
        return compute_returncode(self.queue.cases())

    def on_job_start(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
            return
        fmt = io.StringIO()
        if os.getenv("GITLAB_CI"):
            fmt.write(datetime.datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
        fmt.write("@*{[%s]} " % f"{qrank:0{digits(qsize)}}/{qsize}")
        fmt.write("Starting job @*b{%s}: %s" % (job.id[:7], job.display_name()))
        logger.log(logging.EMIT, fmt.getvalue().strip(), extra={"prefix": ""})

    def on_job_finish(self, job: JobProtocol, qrank: int, qsize: int) -> None:
        if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
            return
        fmt = io.StringIO()
        if os.getenv("GITLAB_CI"):
            fmt.write(datetime.datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
        fmt.write("@*{[%s]} " % f"{qrank:0{digits(qsize)}}/{qsize}")
        fmt.write("Finished job @*b{%s}: %s" % (job.id[:7], job.display_name(status=True)))
        logger.log(logging.EMIT, fmt.getvalue().strip(), extra={"prefix": ""})

    def _check_timeouts(self) -> None:
        """Check for and kill processes that have exceeded their timeout."""
        current_time = time.time()

        for pid, slot in list(self.inflight.items()):
            if slot.proc.is_alive():
                total_timeout = slot.job.timeout * self.timeout_multiplier
                elapsed = current_time - slot.start_time
                if elapsed > total_timeout:
                    # Get measurements before killing
                    measurements = slot.proc.get_measurements()
                    slot.proc.shutdown(signal.SIGTERM, grace_period=0.05)
                    slot.job.refresh()
                    slot.job.set_status("TIMEOUT", reason=f"Job timed out after {total_timeout} s.")
                    slot.job.measurements.update(measurements)
                    slot.job.save()
                    slot.proc.join()
                    self.finished[pid] = self.inflight.pop(pid)
                    self.queue.done(slot.job)
                    self.on_job_finish(slot.job, slot.qrank, slot.qsize)

    def _check_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self._check_timeouts()

        finished_pids = [pid for pid, slot in self.inflight.items() if not slot.proc.is_alive()]

        for pid in finished_pids:
            slot = self.inflight.pop(pid)
            self.finished[pid] = slot

            # Get the final result before cleaning up
            result = None
            try:
                result = slot.queue.get_nowait()
            except (EmptyResultQueue, OSError):
                pass
            except Exception:
                logger.exception(f"Error retrieving result for {slot.job}")

            if result is not None:
                slot.job.on_result(result)
            else:
                slot.job.set_status(
                    "ERROR", reason=f"No result found for job {slot.job} (pid {pid})"
                )

            # Get measurements and store in job
            measurements = slot.proc.get_measurements()
            slot.job.measurements.update(measurements)
            slot.job.save()

            try:
                slot.queue.close()
                slot.queue.join_thread()
            except Exception:  # nosec B110
                pass

            slot.proc.join()  # Clean up the process
            self.queue.done(slot.job)
            self.on_job_finish(slot.job, slot.qrank, slot.qsize)

    def _wait_for_slot(self) -> None:
        """Wait until a process slot is available."""
        while len(self.inflight) >= self.max_workers:
            self._check_finished_processes()
            if len(self.inflight) >= self.max_workers:
                time.sleep(0.05)  # Brief sleep before checking again

    def _wait_all(self, live: "CanaryLive") -> None:
        """Wait for all active processes to complete."""
        while self.inflight:
            self._check_finished_processes()
            if self.inflight:
                time.sleep(0.075)
            live.update()

    def _terminate_all(self, signum: int):
        """Terminate all active processes."""
        for pid, slot in list(self.inflight.items()):
            if slot.proc.is_alive():
                measurements = slot.proc.get_measurements()
                slot.proc.shutdown(signum, grace_period=0.05)
                slot.job.refresh()
                stat = "CANCELLED" if signum == signal.SIGINT else "ERROR"
                slot.job.set_status(stat, f"Job terminated with code {signum}")
                slot.job.measurements.update(measurements)
                slot.job.save()
                self.queue.done(slot.job)
                self.on_job_finish(slot.job, slot.qrank, slot.qsize)

        # Force kill if still alive
        for pid, slot in self.inflight.items():
            if slot.proc.is_alive():
                logger.warning(f"Killing process {pid} (job {slot.job})")
                slot.proc.kill()

        # Clean up
        for slot in self.inflight.values():
            slot.proc.join()

        self.finished.update(self.inflight)
        self.inflight.clear()
        self.queue.clear("CANCELLED" if signum == signal.SIGINT else "ERROR")

    def _check_keyboard_input(self, start: float):
        if key := keyboard.get_key():
            if key in "sS":
                text = self.queue.status(start=start)
                logger.log(logging.EMIT, text, extra={"prefix": ""})
            elif key in "qQ":
                logger.debug(f"Quiting due to caputuring {key!r} from the keyboard")
                self._terminate_all(signal.SIGTERM)
                raise KeyboardInterrupt

    @cached_property
    def timeout_multiplier(self) -> float:
        if cli_timeouts := config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                return float(t)
        elif t := config.get("timeout:multiplier"):
            return float(t)
        return 1.0

    def _render_dashboard(self) -> Table:
        table = Table(expand=True)
        table.add_column("Job")
        table.add_column("ID")
        table.add_column("State")
        table.add_column("Elapsed")
        table.add_column("Rank")

        for slot in sorted(self.finished.values(), key=lambda x: x.qrank):
            elapsed = slot.job.timekeeper.duration
            table.add_row(
                slot.job.display_name(rich=True),
                slot.job.id[:7],
                slot.job.status.display_name(rich=True),
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        now = time.time()
        for slot in sorted(self.inflight.values(), key=lambda x: x.qrank):
            elapsed = now - slot.start_time
            table.add_row(
                slot.job.display_name(rich=True),
                slot.job.id[:7],
                "[green]RUNNING[/green]",
                f"{elapsed:5.1f}s",
                f"{slot.qrank}/{slot.qsize}",
            )

        while len(table.rows) < self.max_workers:
            table.add_row("", "", "", "", "")

        return table


class CanaryLive:
    def __init__(
        self,
        factory: Callable[[], Table],
        *,
        refresh_per_second: int = 4,
        console: Console | None = None,
    ) -> None:
        self.factory = factory
        self.enabled = console is not None
        self.live: Live | None = None
        self.refresh_per_second = refresh_per_second
        self.console = console

        # Logging control
        self._filter = logging.MuteConsoleFilter()
        self._stream_handlers: list[logging.StreamHandler] = []

    def __enter__(self):
        if self.enabled:
            self._mute_stream_handlers()
            self.live = Live(
                self.factory(),
                refresh_per_second=self.refresh_per_second,
                console=self.console,
                transient=False,
            )
            self.live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.live:
            self.live.__exit__(exc_type, exc, tb)
            self._unmute_stream_handlers()

    def update(self) -> None:
        if self.live:
            try:
                self.live.update(self.factory(), refresh=True)
            except BlockingIOError:
                pass

    def _mute_stream_handlers(self) -> None:
        root = logging.builtin_logging.getLogger(logging.root_log_name)
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.addFilter(self._filter)
                self._stream_handlers.append(h)

    def _unmute_stream_handlers(self) -> None:
        for h in self._stream_handlers:
            h.removeFilter(self._filter)
        self._stream_handlers.clear()
