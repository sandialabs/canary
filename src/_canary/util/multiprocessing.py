# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Multiprocessing utilities: process-pool helpers, error propagation, and an FS-backed queue.

Key components: ``map``/``starmap`` wrappers that transparently fall back to
single-process execution for small workloads, ``ErrorFromWorker``/``Task`` for
structured worker-error capture, ``FSQueue`` for disk-backed inter-process
messaging, and ``initialize`` for setting the preferred start method.
"""

import contextlib
import multiprocessing
import multiprocessing.context
import multiprocessing.queues
import multiprocessing.reduction
import os
import pickle  # nosec B403
import sys
import traceback
from multiprocessing.process import BaseProcess
from pathlib import Path
from queue import Empty
from tempfile import NamedTemporaryFile
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Literal
from typing import Sequence
from typing import cast

from . import cpu_count
from . import logging

multiprocess_threshold = 100
default_cpu_count = 8
builtin_map = map
logger = logging.get_logger(__name__)
_initialized: bool = False


StartMethod = Literal["fork", "forkserver", "spawn"]


def max_workers(hint: int = -1) -> int:
    """Return the maximum number of worker processes to use.

    Respects the ``CANARY_MAX_WORKERS`` environment variable.  If ``hint``
    is positive it is used directly (with a warning if it exceeds the CPU count).

    Args:
        hint: Explicit worker count; ``-1`` or ``0`` defers to the default cap.

    Returns:
        Number of worker processes to launch.
    """
    nproc = cpu_count()
    max_default_workers: int
    if var := os.getenv("CANARY_MAX_WORKERS"):
        max_default_workers = int(var)
    else:
        max_default_workers = 30
    n = min(nproc, max_default_workers) if hint <= 0 else hint
    if n > nproc:
        logger.warning(f"workers={n} > cpu_count={nproc}")
    return n


def get_context(method: StartMethod | None = None) -> multiprocessing.context.BaseContext:
    """
    Return a multiprocessing context.

    - If `method` is None: return the process-wide default context
      (whatever was set by initialize()).
    - If `method` is provided: return that specific context.

    This is the safest way to avoid touching private symbols like
    multiprocessing.context._default_context.
    """
    if method is None:
        return multiprocessing.get_context()
    return multiprocessing.get_context(method)


def default_start_method() -> str:
    """Best-effort reporting of the active default start method."""
    try:
        return multiprocessing.get_start_method()
    except RuntimeError:
        # start method not set yet (rare in your code since initialize() sets it)
        return "unset"


def recommended_start_method() -> StartMethod:
    """Return the recommended multiprocessing start method for this platform.

    Prefers ``forkserver`` on Linux when ``send_handle`` is available, ``spawn``
    on macOS and Windows.  Can be overridden with ``CANARY_START_METHOD``.

    Returns:
        One of ``"fork"``, ``"forkserver"``, or ``"spawn"``.

    Raises:
        ValueError: If ``CANARY_START_METHOD`` contains an invalid value.
    """
    if var := os.getenv("CANARY_START_METHOD"):
        if var in ("fork", "forkserver", "spawn"):
            return cast(StartMethod, var)
        raise ValueError(
            "Invalid CANARY_START_METHOD={!r}; expected one of "
            "'fork', 'forkserver', or 'spawn'".format(var)
        )
    # Prefer forkserver on Linux when send_handle is available (same as initialize()).
    if multiprocessing.reduction.HAVE_SEND_HANDLE and sys.platform != "darwin":
        return "forkserver"
    return "spawn"


def initialize() -> None:
    """Set the multiprocessing start method and warm-start the process pool.

    Idempotent: subsequent calls are no-ops.  Calls ``recommended_start_method``
    to choose the start method and spawns a no-op child process to pre-initialize
    the forkserver (if applicable).
    """
    global _initialized
    if _initialized:
        return
    start_method: str = recommended_start_method()
    multiprocessing.set_start_method(start_method, force=True)
    p = multiprocessing.Process(target=_noop)
    p.start()
    p.join()
    _initialized = True


def _noop():
    pass


class SimpleQueue(multiprocessing.queues.SimpleQueue):
    """``multiprocessing.SimpleQueue`` with a default context."""

    def __init__(self, ctx: multiprocessing.context.BaseContext | None = None) -> None:
        super().__init__(ctx=ctx or multiprocessing.context._default_context)


class Queue(multiprocessing.queues.Queue):
    """``multiprocessing.Queue`` with a default context."""

    def __init__(
        self, maxsize: int = 0, ctx: multiprocessing.context.BaseContext | None = None
    ) -> None:
        super().__init__(maxsize=maxsize, ctx=ctx or multiprocessing.context._default_context)


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
        """Return a formatted stacktrace string prefixed with the worker PID."""
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
        """Wrap ``func`` so exceptions are returned as ``ErrorFromWorker`` objects."""
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


def num_processes(max_processes: int | None = None, allow_oversubscription: bool = False) -> int:
    """Return the number of processes in a pool.

    Currently the function return the minimum between the maximum number
    of processes and the cpus available.

    When a maximum number of processes is not specified return the cpus available.

    Args:
        max_processes (int or None): maximum number of processes allowed

    """
    if allow_oversubscription:
        return max(cpu_count(), max_processes or cpu_count())
    return min(cpu_count(), max_processes or cpu_count())


def map(
    func: Callable,
    args: Sequence,
    processes: int | None = None,
    debug: bool = False,
    initializer: Callable[..., Any] | None = None,
    initargs: Iterable[Any] = (),
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
        with pool(
            processes=num_processes(max_processes=processes),
            initializer=initializer,
            intargs=initargs,
        ) as p:
            results = p.map(task_wrapper, args)
    raise_if_errors(*results, debug=debug)
    return results


def starmap(
    func: Callable,
    args: Sequence,
    processes: int | None = None,
    debug: bool = False,
    initializer: Callable[..., Any] | None = None,
    initargs: Iterable[Any] = (),
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
        with pool(
            processes=num_processes(max_processes=processes),
            initializer=initializer,
            initargs=initargs,
        ) as p:
            results = p.starmap(task_wrapper, args)
    raise_if_errors(*results, debug=debug)
    return results


def parent_process() -> BaseProcess | None:
    """Return the parent ``Process`` object, or ``None`` in the main process."""
    return multiprocessing.parent_process()


class FSQueue:
    """
    A file-system-backed queue with caching.

    Items are pickled to disk, multiple processes can safely put items,
    and a listener can consume them in FIFO order.
    """

    def __init__(self, root: Path):
        """Initialize the queue rooted at ``root``, creating the directory if needed."""
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: list[Path] = []

    def put(self, obj: Any) -> None:
        """Serialize and atomically store an object in the queue."""
        temp_file: Path | None = None
        try:
            with NamedTemporaryFile(dir=self.root, delete=False, suffix=".tmp", mode="wb") as tf:
                temp_file = Path(tf.name)
                pickle.dump(obj, tf)
                tf.flush()
                tf.fileno()  # ensure file is written to disk
            final_file = self.root / f"{temp_file.stem}.pkl"
            temp_file.replace(final_file)  # atomic rename
        except Exception as e:
            if temp_file and temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to put item in FSQueue: {e}")

    def _refill_cache(self) -> None:
        """Populate the internal cache from disk, sorted by modification time."""
        files = sorted(self.root.glob("*.pkl"), key=lambda f: f.stat().st_mtime)
        self._cache = files

    def empty(self) -> bool:
        """Return ``True`` if the queue contains no items."""
        if not self._cache:
            self._refill_cache()
        return not bool(self._cache)

    def get(self) -> Any:
        """
        Get the oldest item from the queue.

        Raises:
            Empty: if the queue is empty.
        """
        if not self._cache:
            self._refill_cache()
        if not self._cache:
            raise Empty()
        f = self._cache.pop(0)
        try:
            with f.open("rb") as fh:
                obj = pickle.load(fh)  # nosec B301
            f.unlink(missing_ok=True)
            return obj
        except Exception as e:
            f.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to read item from FSQueue: {e}")

    def drain(self) -> list[Any]:
        """
        Yield items from the queue until empty.
        """
        objs: list[Any] = []
        while True:
            try:
                objs.append(self.get())
            except Empty:
                return objs
