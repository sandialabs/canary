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

from ... import config
from ...error import FailFast
from ...error import StopExecution
from ...queue import Busy as BusyQueue
from ...queue import Empty as EmptyQueue
from ...queue import ResourceQueue
from ...testcase import TestCase
from ...util import keyboard
from ...util import logging
from ...util.filesystem import working_dir
from ...util.procutils import ProcessPoolExecutor
from ...util.procutils import cleanup_children
from ...util.returncode import compute_returncode
from ...util.string import pluralize
from ...util.time import hhmmss
from ...util.time import timestamp
from ..hookspec import hookimpl

global_session_lock = threading.Lock()
logger = logging.get_logger(__name__)


@hookimpl(trylast=True)
def canary_runtests(cases: Sequence[TestCase]) -> int:
    """Run each test case in ``cases``.

    Args:
      cases: test cases to run

    Returns:
      The session returncode (0 for success)

    """
    returncode: int = -10
    atexit.register(cleanup_children)
    queue = ResourceQueue.factory(global_session_lock, cases)
    runner = Runner()
    assert config.get("session:work_tree") is not None
    with working_dir(config.get("session:work_tree")):
        cleanup_queue = True
        try:
            what = pluralize("test case", len(queue))
            logger.info("@*{Running} %d %s" % (len(queue), what))
            start = timestamp()
            stop = -1.0
            logger.debug("Start: processing queue")
            process_queue(runner=runner, queue=queue)
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
            if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
                queue.update_progress_bar(start, last=True)
            returncode = compute_returncode(queue.cases())
            queue.close(cleanup=cleanup_queue)
            stop = timestamp()
            dt = stop - start
            logger.info("@*{Finished} %d %s (%s)" % (len(queue), what, hhmmss(dt)))
            atexit.unregister(cleanup_children)
    return returncode


def process_queue(*, runner: Callable, queue: ResourceQueue) -> None:
    """Process the test queue, asynchronously

    Args:
        queue: the test queue to process

    """
    futures: dict = {}
    start = timestamp()
    duration = lambda: timestamp() - start
    timeout = float(config.get("config:timeout:session", -1))
    qsize = queue.qsize
    qrank = 0
    ppe = None
    progress_bar = (
        config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO
    )
    try:
        config.archive(os.environ)
        with ProcessPoolExecutor(workers=queue.workers) as ppe:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                if key := keyboard.get_key():
                    if key in "sS":
                        logger.log(logging.EMIT, queue.status(start=start), extra={"prefix": ""})
                    elif key in "qQ":
                        ppe.shutdown(cancel_futures=True)
                        cleanup_children()
                        raise KeyboardInterrupt
                if progress_bar:
                    queue.update_progress_bar(start)
                if timeout >= 0.0 and duration() > timeout:
                    raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                try:
                    iid, obj = queue.get()
                    queue.heartbeat()
                except BusyQueue:
                    time.sleep(0.005)
                    continue
                except EmptyQueue:
                    break
                logger.debug(f"Submitting {obj} to process pool for execution")
                future = ppe.submit(runner, obj, qsize=qsize, qrank=qrank)
                qrank += 1
                callback = partial(done_callback, queue, iid)
                future.add_done_callback(callback)
                logger.debug(f"Process pool execution for {obj} finished")
                futures[iid] = (obj, future)
    finally:
        if ppe is not None:
            ppe.shutdown(cancel_futures=True)


class KeyboardQuit(Exception):
    pass


class Runner:
    """Class for running ``AbstractTestCase``."""

    def __call__(self, case: TestCase, *args: str, **kwargs: Any) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        config.ensure_loaded()
        try:
            config.pluginmanager.hook.canary_testcase_setup(case=case)
            config.pluginmanager.hook.canary_testcase_run(
                case=case, qsize=kwargs.get("qsize", 1), qrank=kwargs.get("qrank", 0)
            )
        finally:
            config.pluginmanager.hook.canary_testcase_finish(case=case)


def done_callback(queue: ResourceQueue, iid: int, future: concurrent.futures.Future) -> None:
    """Function registered to the process pool executor to be called when a test completes

    Args:
        queue: the queue
        iid: the queue's internal ID of the test
        future: the future return by the process pool executor

    """
    if future.cancelled():
        return
    try:
        future.result()
    except BrokenProcessPool:
        # The future was probably killed by fail_fast or a keyboard interrupt
        return
    except BrokenPipeError:
        # something bad happened.  On some HPCs we have seen:
        # BrokenPipeError: [Errno 108] Cannot send after transport endpoint shutdown
        # Seems to be a filesystem issue, punt for now
        return

    # The case was run in a subprocess.  The object must be
    # refreshed so that the state in this main thread is up to date.
    obj = queue.done(iid)
    obj.refresh()
    logger.debug(f"Finished {obj} ({obj.duration} s.)")
