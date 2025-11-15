# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import multiprocessing as mp
import os
import time
from functools import cached_property
from pathlib import Path
from queue import Empty as EmptyResultQueue
from typing import Any
from typing import Callable
from uuid import uuid4

from . import config
from .queue import AbstractResourceQueue
from .queue import Busy
from .queue import Empty
from .util import cpu_count
from .util import keyboard
from .util import logging
from .util.procutils import MeasuredProcess
from .util.returncode import compute_returncode

logger = logging.get_logger(__name__)


class ResourceQueueExecutor:
    """Manages a pool of worker processes with timeout support and metrics collection."""

    def __init__(self, queue: AbstractResourceQueue, runner: Callable, busy_wait_time: float = 0.5):
        """
        Initialize the process pool.

        Args:
            max_workers: Maximum number of concurrent worker processes
            queue: ResourceQueue instance
            runner: Callable that processes cases
            busy_wait_time: Time to wait when queue is busy
        """
        self.max_workers = queue.workers
        if self.max_workers > cpu_count():
            logger.warning(f"workers={self.max_workers} > cpu_count={cpu_count()}")

        self.queue: AbstractResourceQueue = queue
        self.runner = runner
        self.busy_wait_time = busy_wait_time

        # Map: pid -> (MeasuredProcess, result_queue, job, start_time, timeout)
        self.inflight: dict[int, tuple[MeasuredProcess, mp.Queue, Any, float, float]] = {}
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

        qsize = len(self.queue)
        qrank = 0
        start = time.time()
        while True:
            try:
                if timeout >= 0.0 and time.time() - start > timeout:
                    raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")

                self._check_keyboard_input(start)

                # Clean up any finished processes and collect results
                self._clean_finished_processes()

                # Wait for a slot if at max capacity
                self._wait_for_slot()

                # Get a job from the queue
                job = self.queue.get()

                # Create a result queue for this specific process
                result_queue = mp.Queue()

                # Launch a new measured process
                proc = MeasuredProcess(
                    target=self.runner,
                    args=(job, result_queue),
                    kwargs={"qsize": qsize, "qrank": qrank, **kwargs},
                )

                proc.start()
                qrank += 1

                # Store process with its result queue, job, start time, and timeout
                job_timeout = job.timeout * self.timeout_multiplier
                self.inflight[proc.pid] = (proc, result_queue, job, time.time(), job_timeout)

            except Busy:
                # Queue is busy, wait and try again
                time.sleep(self.busy_wait_time)

            except Empty:
                # Queue is empty, wait for remaining jobs and exit
                self._wait_all()
                break

            except KeyboardInterrupt:
                self._terminate_all()
                break

            except BaseException:
                logger.exception("Unhandled exception in process pool")
                raise

        return compute_returncode(self.queue.cases())

    def check_timeouts(self) -> None:
        """Check for and kill processes that have exceeded their timeout."""
        current_time = time.time()

        for pid, (proc, _, job, start_time, timeout) in list(self.inflight.items()):
            if proc.is_alive():
                elapsed = current_time - start_time
                if elapsed > timeout:
                    # Get measurements before killing
                    measurements = proc.get_measurements()
                    job.measurements.update(measurements)

                    proc.kill()
                    proc.join()

                    # Remove from active processes
                    self.inflight.pop(pid)

                    # Send timeout result
                    job.status.set(
                        "TIMEOUT",
                        message=f"Process exceeded timeout of {timeout} seconds",
                    )
                    self.queue.done(job)
                    job.save()

    def _clean_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self.check_timeouts()

        finished_pids = [
            pid for pid, (proc, _, _, _, _) in self.inflight.items() if not proc.is_alive()
        ]

        for pid in finished_pids:
            proc, result_queue, job, _, _ = self.inflight.pop(pid)

            # Get measurements and store in job
            measurements = proc.get_measurements()
            job.measurements.update(measurements)

            # Get the final result before cleaning up
            result = None
            try:
                result = result_queue.get_nowait()
            except (EmptyResultQueue, OSError):
                pass
            except Exception:
                logger.exception(f"Error retrieving result for {job}")

            if result is not None:
                job.update(**result)
            else:
                logger.error(f"No result found for job {job} (pid {pid})")

            try:
                result_queue.close()
                result_queue.join_thread()
            except Exception:
                pass

            proc.join()  # Clean up the process
            self.queue.done(job)
            job.save()
            logger.debug(f"Process {pid} finished and cleaned up")

    def _wait_for_slot(self) -> None:
        """Wait until a process slot is available."""
        while len(self.inflight) >= self.max_workers:
            self._clean_finished_processes()
            if len(self.inflight) >= self.max_workers:
                time.sleep(0.1)  # Brief sleep before checking again

    def _wait_all(self) -> None:
        """Wait for all active processes to complete."""
        while self.inflight:
            self._clean_finished_processes()
            if self.inflight:
                time.sleep(0.1)

    def _terminate_all(self):
        """Terminate all active processes."""
        for pid, (proc, _, job, _, _) in self.inflight.items():
            if proc.is_alive():
                logger.warning(f"Terminating process {pid} (job {job})")
                proc.terminate()
                self.queue.done(job)
                job.save()

        # Give processes time to terminate gracefully
        time.sleep(1)

        # Force kill if still alive
        for pid, (proc, result_queue, job, start_time, timeout) in self.inflight.items():
            if proc.is_alive():
                logger.warning(f"Killing process {pid} (job {job})")
                proc.kill()

        # Clean up
        for proc, result_queue, job, start_time, timeout in self.inflight.values():
            proc.join()

        self.inflight.clear()

    def _check_keyboard_input(self, start: float):
        if key := keyboard.get_key():
            if key in "sS":
                text = self.queue.status(start=start)
                logger.log(logging.EMIT, text, extra={"prefix": ""})
            elif key in "qQ":
                logger.debug(f"Quiting due to caputuring {key!r} from the keyboard")
                self._terminate_all()
                raise KeyboardInterrupt

    @cached_property
    def timeout_multiplier(self) -> float:
        if cli_timeouts := config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                return float(t)
        elif t := config.get("timeout:multiplier"):
            return float(t)
        return 1.0
