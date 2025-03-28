# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import contextlib
import multiprocessing
import os
import sys
import traceback
from multiprocessing.process import BaseProcess
from typing import Any
from typing import Callable
from typing import Sequence

from ..util.rprobe import cpu_count

multiprocess_threshold = 100
default_cpu_count = 8
builtin_map = map


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
    try:
        p = multiprocessing.Pool(*args, **kwargs)
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
