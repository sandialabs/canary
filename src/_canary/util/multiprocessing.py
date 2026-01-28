# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import contextlib
import multiprocessing
import multiprocessing.context
import multiprocessing.queues
import multiprocessing.reduction
import multiprocessing.shared_memory
import os
import pickle  # nosec B403
import sys
import time
import traceback
from multiprocessing.process import BaseProcess
from typing import Any
from typing import Callable
from typing import Sequence

import psutil

from . import cpu_count
from . import logging

multiprocess_threshold = 100
default_cpu_count = 8
builtin_map = map

logger = logging.get_logger(__name__)


def put_in_shared_memory(obj: Any) -> tuple[str, int]:
    data = pickle.dumps(obj)
    size = len(data)
    shared_mem = multiprocessing.shared_memory.SharedMemory(create=True, size=size)
    shared_mem.buf[:size] = data  # type: ignore
    return shared_mem.name, size


def get_from_shared_memory(name: str, size: int) -> Any:
    shared_mem = multiprocessing.shared_memory.SharedMemory(name=name)
    data = bytes(shared_mem.buf[:size])  # type: ignore
    return pickle.loads(data)  # nosec B301


def unlink_shared_memory(name: str) -> None:
    shared_mem = multiprocessing.shared_memory.SharedMemory(name=name)
    shared_mem.unlink()


def initialize() -> None:
    start_method: str
    if var := os.getenv("CANARY_MULTIPROCESSING_START_METHOD"):
        start_method = var
    elif multiprocessing.reduction.HAVE_SEND_HANDLE and sys.platform != "darwin":
        start_method = "forkserver"
    else:
        start_method = "spawn"
    multiprocessing.set_start_method(start_method, force=True)
    p = multiprocessing.Process(target=_noop)
    p.start()
    p.join()


def _noop():
    pass


class SimpleQueue(multiprocessing.queues.SimpleQueue):
    def __init__(self) -> None:
        super().__init__(ctx=multiprocessing.context._default_context)


class Queue(multiprocessing.queues.Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize, ctx=multiprocessing.context._default_context)


class MeasuredProcess(multiprocessing.Process):
    """A Process subclass that collects resource usage metrics using psutil.
    Metrics are sampled each time is_alive() is called.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.samples = []
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
                except Exception:
                    pass  # nosec B110

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

    def shutdown(self, signum: int, grace_period: float = 0.05) -> None:
        logger.debug(f"Terminating process {self.pid}")
        self._sample_metrics()
        if self.pid is not None:
            os.kill(self.pid, signum)
        time.sleep(grace_period)
        self.kill()


def get_process_metrics(
    proc: psutil.Popen, metrics: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    # Collect process information
    metrics = metrics or {}
    try:
        valid_names = set(getattr(psutil, "_as_dict_attrnames", []))
        skip_names = {
            "cmdline",
            "cpu_affinity",
            "net_connections",
            "cwd",
            "environ",
            "exe",
            "gids",
            "ionice",
            "memory_full_info",
            "memory_maps",
            "threads",
            "name",
            "nice",
            "pid",
            "ppid",
            "status",
            "terminal",
            "uids",
            "username",
        }
        names = valid_names - skip_names
        new_metrics = proc.as_dict(names)
    except psutil.NoSuchProcess:
        logger.debug(f"Process with PID {proc.pid} does not exist.")
    except psutil.AccessDenied:
        logger.debug(f"Access denied to process with PID {proc.pid}.")
    except psutil.ZombieProcess:
        logger.debug(f"Process with PID {proc.pid} is a Zombie process.")
    else:
        for name, metric in new_metrics.items():
            if name == "open_files":
                files = metrics.setdefault("open_files", [])
                for f in metric:
                    if f[0] not in files:
                        files.append(f[0])
            elif name == "cpu_times":
                metrics["cpu_times"] = {"user": metric.user, "system": metric.system}
            elif name in ("num_threads", "cpu_percent", "num_fds", "memory_percent"):
                n = metrics.setdefault(name, 0)
                metrics[name] = max(n, metric)
            elif name == "memory_info":
                for key, val in metric._asdict().items():
                    n = metrics.setdefault(name, {}).setdefault(key, 0)
                    metrics[name][key] = max(n, val)
            elif hasattr(metric, "_asdict"):
                metrics[name] = dict(metric._asdict())
            else:
                metrics[name] = metric
    finally:
        return metrics


class ErrorFromWorker:
    """Wrapper class to report an error from a worker process"""

    def __init__(self, exc_cls, exc, tb):
        """Create an error object from an exception raised from
        the worker process.

        The attributes of the process error objects are all strings
        as they are easy to send over a pipe.

        Args:
            exc: exception raised from the worker process
        """
        self.pid = os.getpid()
        self.error_message = str(exc)
        self.stacktrace_message = "".join(traceback.format_exception(exc_cls, exc, tb))

    @property
    def stacktrace(self):
        msg = "[PID={0.pid}] {0.stacktrace_message}"
        return msg.format(self)

    def __str__(self):
        return self.error_message


class Task:
    """Wrapped task that trap every Exception and return it as an
    ErrorFromWorker object.

    We are using a wrapper class instead of a decorator since the class
    is pickleable, while a decorator with an inner closure is not.
    """

    def __init__(self, func: Callable):
        self.func = func

    def __call__(self, *args: Any) -> Any:
        try:
            value = self.func(*args)
        except Exception:
            value = ErrorFromWorker(*sys.exc_info())
        return value


def raise_if_errors(*results, debug=False):
    """Analyze results from worker Processes to search for ErrorFromWorker
    objects. If found print all of them and raise an exception.

    Args:
        *results: results from worker processes
        debug: if True show complete stacktraces

    Raises:
        RuntimeError: if ErrorFromWorker objects are in the results
    """
    errors = [x for x in results if isinstance(x, ErrorFromWorker)]
    if not errors:
        return

    msg = "\n".join([error.stacktrace if debug else str(error) for error in errors])

    error_fmt = "{0}"
    if len(errors) > 1 and not debug:
        error_fmt = "errors occurred during parallel execution:\n{0}"

    raise RuntimeError(error_fmt.format(msg))


@contextlib.contextmanager
def pool(*args, **kwargs):
    """Context manager to start and terminate a pool of processes

    Arguments are forwarded to the multiprocessing.Pool.__init__ method.
    """
    p = multiprocessing.Pool(*args, **kwargs)
    try:
        yield p
    finally:
        p.terminate()
        p.join()


def num_processes(max_processes: int | None = None, _cache: dict = {}) -> int:
    """Return the number of processes in a pool.

    Currently the function return the minimum between the maximum number
    of processes and the cpus available.

    When a maximum number of processes is not specified return the cpus available.

    Args:
        max_processes (int or None): maximum number of processes allowed

    """
    if max_processes in _cache:
        return _cache[max_processes]
    n = min(cpu_count(), max_processes or cpu_count())
    _cache[max_processes] = n
    return n


def map(
    func: Callable,
    args: Sequence,
    processes: int | None = None,
    debug: bool = False,
) -> Any:
    """Map a func to the list of arguments, return the list of results.

    Args:
      func: user defined task object
      args: iterator of arguments for the task
      processes: maximum number of processes allowed
      debug: if False, raise an exception containing just the error messages from
        workers, if True an exception with complete stacktraces

    Raises:
      RuntimeError: if any error occurred in the worker processes

    """
    task_wrapper = Task(func)
    if len(args) < multiprocess_threshold or sys.platform == "win32":
        results = list(builtin_map(task_wrapper, args))
    else:
        with pool(processes=num_processes(max_processes=processes)) as p:
            results = p.map(task_wrapper, args)
    raise_if_errors(*results, debug=debug)
    return results


def starmap(
    func: Callable,
    args: Sequence,
    processes: int | None = None,
    debug: bool = False,
) -> Any:
    """Map a func to the list of arguments, return the list of results.

    Args:
      func: user defined task object
      args: list of arguments for the task
      processes: maximum number of processes allowed
      debug: if False, raise an exception containing just the error messages from
        workers, if True an exception with complete stacktraces

    Raises:
      RuntimeError: if any error occurred in the worker processes

    """
    task_wrapper = Task(func)
    if len(args) < multiprocess_threshold or sys.platform == "win32":
        results = [task_wrapper(*arg) for arg in args]
    else:
        with pool(processes=num_processes(max_processes=processes)) as p:
            results = p.starmap(task_wrapper, args)
    raise_if_errors(*results, debug=debug)
    return results


def parent_process() -> BaseProcess | None:
    return multiprocessing.parent_process()
