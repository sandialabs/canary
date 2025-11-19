# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import datetime
import io
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

from . import config
from .protocols import JobProtocol
from .queue import Busy
from .queue import Empty
from .queue import ResourceQueue
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


def with_traceback(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        case = args[0]
        case.status.set("ERROR", message=f"{e.__class__.__name__}({e.args[0]})")

        queue = args[1]

        while not queue.empty():
            queue.get_nowait()

        queue.put({"status": case.status})
        str = io.StringIO()
        traceback.print_exc(file=str)
        logger.error("Child process failed")
        logger.debug(f"Child process failed: {str.getvalue()}")
        sys.exit(1)


class ResourceQueueExecutor:
    """Manages a pool of worker processes with timeout support and metrics collection."""

    def __init__(
        self,
        queue: ResourceQueue,
        runner: Callable,
        max_workers: int = -1,
        busy_wait_time: float = 0.5,
    ):
        """
        Initialize the process pool.

        Args:
            max_workers: Maximum number of concurrent worker processes
            queue: ResourceQueue instance
            runner: Callable that processes cases
            busy_wait_time: Time to wait when queue is busy
        """
        self.max_workers = max_workers if max_workers > 0 else os.cpu_count()
        if self.max_workers > os.cpu_count():
            logger.warning(f"workers={self.max_workers} > cpu_count={os.cpu_count()}")

        self.queue: ResourceQueue = queue
        self.runner = runner
        self.busy_wait_time = busy_wait_time

        self.inflight: dict[int, ExecutionSlot] = {}
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

        logger.info(f"Starting process pool with max {self.max_workers} workers")

        timeout = float(config.get("timeout:session", -1))
        qrank, qsize = 0, len(self.queue)
        start = time.time()
        while True:
            try:
                if timeout >= 0.0 and time.time() - start > timeout:
                    self._terminate_all(signal.SIGUSR2)
                    raise TimeoutError(f"Test session exceeded time out of {timeout} s.")

                self._check_keyboard_input(start)

                # Clean up any finished processes and collect results
                self._check_finished_processes()

                # Wait for a slot if at max capacity
                self._wait_for_slot()

                # Get a job from the queue
                job = self.queue.get()
                qrank += 1

                # Create a result queue for this specific process
                result_queue = mp.Queue()

                # Launch a new measured process
                proc = MeasuredProcess(
                    target=with_traceback,
                    args=(self.runner, job, result_queue),
                    kwargs=kwargs,
                )
                proc.start()
                self.on_job_start(job, qrank, qsize)

                self.inflight[proc.pid] = ExecutionSlot(
                    proc=proc,
                    queue=result_queue,
                    job=job,
                    start_time=time.time(),
                    qrank=qrank,
                    qsize=qsize,
                )

            except Busy:
                # Queue is busy, wait and try again
                time.sleep(self.busy_wait_time)

            except Empty:
                # Queue is empty, wait for remaining jobs and exit
                self._wait_all()
                break

            except KeyboardInterrupt:
                self._terminate_all(signal.SIGINT)
                break

            except TimeoutError:
                break

            except BaseException:
                logger.exception("Unhandled exception in process pool")
                raise

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
                    slot.proc.shutdown(signal.SIGTERM, grace_period=0.1)
                    slot.job.refresh()
                    slot.job.set_status(
                        "TIMEOUT", message=f"Job timed out after {total_timeout} s."
                    )
                    slot.job.measurements.update(measurements)
                    slot.job.save()
                    slot.proc.join()
                    self.inflight.pop(pid)
                    self.queue.done(slot.job)
                    self.on_job_finish(slot.job, slot.qrank, slot.qsize)

    def _check_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self._check_timeouts()

        finished_pids = [pid for pid, slot in self.inflight.items() if not slot.proc.is_alive()]

        for pid in finished_pids:
            slot = self.inflight.pop(pid)

            # Get measurements and store in job
            measurements = slot.proc.get_measurements()
            slot.job.measurements.update(measurements)

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
                    "ERROR", message=f"No result found for job {slot.job} (pid {pid})"
                )
            slot.job.save()

            try:
                slot.queue.close()
                slot.queue.join_thread()
            except Exception:
                pass

            slot.proc.join()  # Clean up the process
            self.queue.done(slot.job)
            self.on_job_finish(slot.job, slot.qrank, slot.qsize)

    def _wait_for_slot(self) -> None:
        """Wait until a process slot is available."""
        while len(self.inflight) >= self.max_workers:
            self._check_finished_processes()
            if len(self.inflight) >= self.max_workers:
                time.sleep(0.1)  # Brief sleep before checking again

    def _wait_all(self) -> None:
        """Wait for all active processes to complete."""
        while self.inflight:
            self._check_finished_processes()
            if self.inflight:
                time.sleep(0.05)

    def _terminate_all(self, signum: int):
        """Terminate all active processes."""
        for pid, slot in self.inflight.items():
            if slot.proc.is_alive():
                measurements = slot.proc.get_measurements()
                slot.proc.shutdown(signum, grace_period=0.1)
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

        self.inflight.clear()

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
