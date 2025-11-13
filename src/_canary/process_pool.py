import multiprocessing as mp
import time
from functools import cached_property
from typing import Callable

import psutil

from . import config
from .queue import AbstractResourceQueue
from .queue import Busy
from .queue import Empty
from .testcase import TestCase
from .util import keyboard
from .util import logging

logger = logging.get_logger(__name__)


class MeasuredProcess(mp.Process):
    """A Process subclass that collects resource usage metrics using psutil.
    Metrics are sampled each time is_alive() is called.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.samples: list[dict[str, float]] = []
        self._psutil_process = None
        self._start_time = None

    def start(self):
        """Start the process and initialize psutil monitoring."""
        super().start()
        self._start_time = time.time()
        try:
            self._psutil_process = psutil.Process(self.pid)
        except Exception:
            logger.warning(f"Could not attach psutil to process {self.pid}")
            self._psutil_process = None

    def _sample_metrics(self):
        """Sample current process metrics."""
        if not psutil or not self._psutil_process:
            return

        try:
            # Get process info
            with self._psutil_process.oneshot():
                cpu_percent = self._psutil_process.cpu_percent()
                mem_info = self._psutil_process.memory_info()

                sample = {
                    "timestamp": time.time(),
                    "cpu_percent": cpu_percent,
                    "memory_rss_mb": mem_info.rss / (1024 * 1024),  # RSS in MB
                    "memory_vms_mb": mem_info.vms / (1024 * 1024),  # VMS in MB
                }

                # Add number of threads if available
                try:
                    sample["num_threads"] = self._psutil_process.num_threads()
                except:
                    pass

                self.samples.append(sample)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process may have terminated
            pass
        except Exception as e:
            logger.debug(f"Error sampling metrics: {e}")

    def is_alive(self):
        """Check if process is alive and sample metrics."""
        alive = super().is_alive()
        if alive:
            self._sample_metrics()
        return alive

    def get_measurements(self):
        """Calculate statistics from collected samples.
        Returns a dict with min, max, avg for each metric.
        """
        if not self.samples:
            return {
                "duration": time.time() - self._start_time if self._start_time else 0,
                "samples": 0,
            }

        measurements = {
            "duration": time.time() - self._start_time if self._start_time else 0,
            "samples": len(self.samples),
        }

        # Calculate stats for each metric
        metrics = ["cpu_percent", "memory_rss_mb", "memory_vms_mb", "num_threads"]

        for metric in metrics:
            values = [s[metric] for s in self.samples if metric in s]
            if values:
                measurements.setdefault(metric, {})["min"] = min(values)
                measurements.setdefault(metric, {})["max"] = max(values)
                measurements.setdefault(metric, {})["ave"] = sum(values) / len(values)

        return measurements


class ProcessPool:
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
        self.queue: AbstractResourceQueue = queue
        self.runner = runner
        self.busy_wait_time = busy_wait_time

        # Map: pid -> (MeasuredProcess, result_queue, case, start_time, timeout)
        self.inflight: dict[int, tuple[MeasuredProcess, mp.Queue, TestCase, float, float]] = {}

    def check_timeouts(self) -> None:
        """Check for and kill processes that have exceeded their timeout."""
        current_time = time.time()

        for pid, (proc, _, case, start_time, timeout) in list(self.inflight.items()):
            if proc.is_alive():
                elapsed = current_time - start_time
                if elapsed > timeout:
                    # Get measurements before killing
                    measurements = proc.get_measurements()
                    case.measurements.update(measurements)

                    proc.kill()
                    proc.join()

                    # Remove from active processes
                    self.inflight.pop(pid)

                    # Send timeout result
                    case.status.set(
                        "TIMEOUT",
                        message=f"Process exceeded timeout of {timeout} seconds",
                    )
                    self.queue.done(case)
                    case.save()

    def clean_finished_processes(self) -> None:
        """Remove finished processes from the active dict and collect their results."""
        # First check for timeouts
        self.check_timeouts()

        finished_pids = [
            pid for pid, (proc, _, _, _, _) in self.inflight.items() if not proc.is_alive()
        ]

        for pid in finished_pids:
            proc, result_queue, case, _, _ = self.inflight.pop(pid)

            # Get measurements and store in case
            measurements = proc.get_measurements()
            case.measurements.update(measurements)

            # Get the final result before cleaning up
            try:
                result = result_queue.get_nowait()
                case.update(**result)
            except Exception:
                logger.exception(f"No result found for case {case} (pid {pid})")

            proc.join()  # Clean up the process
            self.queue.done(case)
            case.save()
            logger.debug(f"Process {pid} finished and cleaned up")

    def wait_for_slot(self) -> None:
        """Wait until a process slot is available."""
        while len(self.inflight) >= self.max_workers:
            self.clean_finished_processes()
            if len(self.inflight) >= self.max_workers:
                time.sleep(0.1)  # Brief sleep before checking again

    def run(self) -> None:
        """Main loop: get cases from queue and launch processes."""
        logger.info(f"Starting process pool with max {self.max_workers} workers")

        qsize = len(self.queue)
        qrank = 0
        start = time.time()
        while True:
            try:
                self.check_keyboard_input(start)

                # Clean up any finished processes and collect results
                self.clean_finished_processes()

                # Wait for a slot if at max capacity
                self.wait_for_slot()

                # Get a case from the queue
                case = self.queue.get()

                # Create a result queue for this specific process
                result_queue = mp.Queue()

                # Launch a new measured process
                proc = MeasuredProcess(
                    target=self.runner,
                    args=(case, result_queue),
                    kwargs={"qsize": qsize, "qrank": qrank},
                )

                proc.start()
                qrank += 1

                # Store process with its result queue, case, start time, and timeout
                timeout = case.timeout * self.timeout_multiplier
                self.inflight[proc.pid] = (proc, result_queue, case, time.time(), timeout)

            except Busy:
                # Queue is busy, wait and try again
                time.sleep(self.busy_wait_time)

            except Empty:
                # Queue is empty, wait for remaining jobs and exit
                self.wait_all()
                break

            except KeyboardInterrupt:
                self.terminate_all()
                break

    def wait_all(self) -> None:
        """Wait for all active processes to complete."""
        while self.inflight:
            self.clean_finished_processes()
            if self.inflight:
                time.sleep(0.1)

    def terminate_all(self):
        """Terminate all active processes."""
        for pid, (proc, _, case, _, _) in self.inflight.items():
            if proc.is_alive():
                logger.warning(f"Terminating process {pid} (case {case})")
                proc.terminate()
                self.queue.done(case)
                case.save()

        # Give processes time to terminate gracefully
        time.sleep(1)

        # Force kill if still alive
        for pid, (proc, result_queue, case, start_time, timeout) in self.inflight.items():
            if proc.is_alive():
                logger.warning(f"Killing process {pid} (case {case})")
                proc.kill()

        # Clean up
        for proc, result_queue, case, start_time, timeout in self.inflight.values():
            proc.join()

        self.inflight.clear()

    def check_keyboard_input(self, start: float):
        if key := keyboard.get_key():
            if key in "sS":
                text = self.queue.status(start=start)
                logger.log(logging.EMIT, text, extra={"prefix": ""})
            elif key in "qQ":
                logger.debug(f"Quiting due to caputuring {key!r} from the keyboard")
                self.terminate_all()
                raise KeyboardInterrupt

    @cached_property
    def timeout_multiplier(self) -> float:
        timeoutx: float = config.get("config:timeout:multiplier") or 1.0
        timeouts = config.getoption("timeout") or {}
        if t := timeouts.get("multiplier"):
            timeoutx = float(t)
        return timeoutx
