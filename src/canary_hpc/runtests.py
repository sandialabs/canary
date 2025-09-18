# G Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import atexit
import concurrent.futures
import os
import signal
import threading
import time
from concurrent.futures.process import BrokenProcessPool
from functools import partial
from typing import Any
from typing import Callable
from typing import Sequence

import hpc_connect

import canary
from _canary.error import FailFast
from _canary.error import StopExecution
from _canary.queue import Busy as BusyQueue
from _canary.queue import Empty as EmptyQueue
from _canary.util import keyboard
from _canary.util import logging
from _canary.util.procutils import ProcessPoolExecutor
from _canary.util.procutils import cleanup_children
from _canary.util.returncode import compute_returncode

from .queue import ResourceQueue
from .testbatch import TestBatch

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


def runtests(*, backend: hpc_connect.HPCSubmissionManager, cases: Sequence[canary.TestCase]) -> int:
    """Run each test case in ``cases``.

    Args:
      cases: test cases to run

    Returns:
      The session returncode (0 for success)

    """
    returncode: int = -10
    atexit.register(cleanup_children)
    queue = ResourceQueue.factory(global_lock, cases)
    nbatches = len(queue)
    runner = Runner()
    pbar = canary.config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO
    assert canary.config.get("session:work_tree") is not None
    with canary.filesystem.working_dir(canary.config.get("session:work_tree")):
        cleanup_queue = True
        try:
            what = canary.string.pluralize("batch", nbatches)
            logger.info("@*{Running} %d %s" % (nbatches, what))
            start = canary.time.timestamp()
            stop = -1.0
            logger.debug("Start: processing queue")
            process_queue(backend=backend, runner=runner, queue=queue)
        except KeyboardInterrupt:
            logger.debug("keyboard interrupt: killing child processes and exiting")
            returncode = signal.SIGINT.value
            cleanup_queue = False
            raise
        except StopExecution as e:
            logger.debug("stop execution: killing child processes and exiting")
            returncode = e.exit_code
        except FailFast as e:
            logger.debug("fail fast: killing child processes and exiting")
            code = compute_returncode(e.failed)
            returncode = code
            cleanup_queue = False
            names = ",".join(_.name for _ in e.failed)
            raise StopExecution(f"fail_fast: {names}", code)
        except Exception:
            logger.exception("unknown failure: killing child processes and exiting")
            returncode = compute_returncode(queue.cases())
            raise
        else:
            if pbar:
                queue.update_progress_bar(start, last=True)
            returncode = compute_returncode(queue.cases())
            queue.close(cleanup=cleanup_queue)
            stop = canary.time.timestamp()
            dt = stop - start
            logger.info("@*{Finished} %d %s (%s)" % (nbatches, what, canary.time.hhmmss(dt)))
            atexit.unregister(cleanup_children)
    return returncode


def process_queue(
    *, backend: hpc_connect.HPCSubmissionManager, runner: Callable, queue: ResourceQueue
) -> None:
    """Process the test queue, asynchronously

    Args:
        queue: the test queue to process

    """
    futures: dict = {}
    start = canary.time.timestamp()
    duration = lambda: canary.time.timestamp() - start
    timeout = float(canary.config.get("config:timeout:session", -1))
    qsize = queue.qsize
    qrank = 0
    ppe = None
    pbar = canary.config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO
    mark = time.monotonic()
    try:
        canary.config.archive(os.environ)
        with ProcessPoolExecutor(workers=queue.workers) as ppe:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                if key := keyboard.get_key():
                    if key in "sS":
                        logger.log(logging.EMIT, queue.status(start=start), extra={"prefix": ""})
                    elif key in "qQ":
                        logger.debug(f"Quiting due to caputuring {key!r} from the keyboard")
                        ppe.shutdown(cancel_futures=True)
                        cleanup_children()
                        raise KeyboardInterrupt
                if pbar:
                    queue.update_progress_bar(start)
                if timeout >= 0.0 and duration() > timeout:
                    raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                try:
                    iid, obj = queue.get()
                    queue.heartbeat()
                except BusyQueue:
                    time.sleep(0.005)
                    if time.monotonic() - mark > 30:
                        logger.debug("Waiting on busy queue...")
                        mark = time.monotonic()
                    continue
                except EmptyQueue:
                    break
                logger.debug(f"Submitting {obj} to process pool for execution")
                future = ppe.submit(runner, obj, backend.name, qsize=qsize, qrank=qrank)
                qrank += 1
                callback = partial(done_callback, queue, iid)
                future.add_done_callback(callback)
                futures[iid] = (obj, future)
    finally:
        if ppe is not None:
            ppe.shutdown(cancel_futures=True)


class KeyboardQuit(Exception):
    pass


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(self, batch: TestBatch, backend_name: str, *args: str, **kwargs: Any) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        canary.config.ensure_loaded()
        backend = hpc_connect.get_backend(backend_name)
        batch.save()
        batch.run(backend=backend, qsize=kwargs.get("qsize", 1), qrank=kwargs.get("qrank", 0))


def done_callback(queue: ResourceQueue, iid: int, future: concurrent.futures.Future) -> None:
    """Function registered to the process pool executor to be called when a test (or batch of
    tests) completes

    Args:
        iid: the queue's internal ID of the test (or batch)
        queue: the active test queue
        future: the future return by the process pool executor

    """
    if future.cancelled():
        return
    try:
        logger.debug(f"Retrieving future for Batch({iid})")
        future.result()
    except BrokenProcessPool:
        # The future was probably killed by fail_fast or a keyboard interrupt
        logger.debug("BrokenProcessPool occurred while attempting to retrieve future")
        return
    except BrokenPipeError:
        # something bad happened.  On some HPCs we have seen:
        # BrokenPipeError: [Errno 108] Cannot send after transport endpoint shutdown
        # Seems to be a filesystem issue, punt for now
        logger.debug("BrokenPipeError occurred while attempting to retrieve future")
        return

    # The case (or batch) was run in a subprocess.  The object must be
    # refreshed so that the state in this main thread is up to date.
    batch: TestBatch = queue.done(iid)
    if not isinstance(batch, TestBatch):
        logger.error(f"Expected AbstractTestCase, got {batch.__class__.__name__}")
        return
    batch.refresh()
    logger.debug(f"Finished {batch} ({batch.duration} s.)")
    failed: list[canary.TestCase] = []
    for case in batch:
        if case.status == "running":
            # Job was cancelled
            case.status.set("cancelled", "batch cancelled")
        elif case.status == "skipped":
            pass
        elif case.status == "ready":
            case.status.set("not_run", "test not run for unknown reasons")
        elif case.start > 0 and case.stop < 0:
            case.status.set("cancelled", "test case cancelled")
        if not case.status.satisfies(("skipped", "success")):
            failed.append(case)
    if canary.config.getoption("fail_fast") and failed:
        raise FailFast(failed=failed)
    logger.debug(f"Process pool execution for {batch} finished")
