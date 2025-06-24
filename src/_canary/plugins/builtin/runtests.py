# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import atexit
import io
import json
import multiprocessing
import os
import signal
import threading
import time
import traceback
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from datetime import datetime
from functools import partial
from typing import Any
from typing import Generator

from ... import config
from ...error import FailFast
from ...error import StopExecution
from ...queues import BatchResourceQueue
from ...queues import Busy as BusyQueue
from ...queues import Empty as EmptyQueue
from ...queues import ResourceQueue
from ...test.batch import TestBatch
from ...test.case import TestCase
from ...third_party.color import colorize
from ...util import keyboard
from ...util import logging
from ...util.compression import compress64
from ...util.filesystem import mkdirp
from ...util.filesystem import working_dir
from ...util.procutils import cleanup_children
from ...util.returncode import compute_returncode
from ...util.string import pluralize
from ...util.time import hhmmss
from ...util.time import timestamp
from ..hookspec import hookimpl

global_session_lock = threading.Lock()


@hookimpl(trylast=True)
def canary_runtests(cases: list[TestCase], fail_fast: bool = False) -> int:
    """Run each test case in ``cases``.

    Args:
      cases: test cases to run
      fail_fast: If ``True``, stop the execution at the first detected test failure, otherwise
        continuing running until all tests have been run.

    Returns:
      The session returncode (0 for success)

    """
    returncode: int = -10
    atexit.register(cleanup_children)
    queue = setup_queue(cases, fail_fast=fail_fast)
    with rc_environ():
        assert config.session.work_tree is not None
        with working_dir(config.session.work_tree):
            cleanup_queue = True
            try:
                queue_size = len(queue)
                what = pluralize(
                    "batch" if isinstance(queue, BatchResourceQueue) else "test case",
                    queue_size,
                )
                logging.info(colorize("@*{Running} %d %s" % (queue_size, what)))
                start = timestamp()
                stop = -1.0
                logging.debug("Start: processing queue")
                process_queue(queue=queue)
            except ProcessPoolExecutorFailedToStart:
                if config.session.level:
                    # This can happen when the ProcessPoolExecutor fails to obtain a lock.
                    returncode = -3
                    for case in queue.cases():
                        case.status.set("retry")
                        case.save()
                else:
                    returncode = compute_returncode(queue.cases())
                raise
            except KeyboardInterrupt:
                logging.debug("keyboard interrupt: killing child processes and exiting")
                returncode = signal.SIGINT.value
                cleanup_queue = False
                raise
            except StopExecution as e:
                logging.debug("stop execution: killing child processes and exiting")
                returncode = e.exit_code
            except FailFast as e:
                logging.debug("fail fast: killing child processes and exiting")
                code = compute_returncode(e.failed)
                returncode = code
                cleanup_queue = False
                names = ",".join(_.name for _ in e.failed)
                raise StopExecution(f"fail_fast: {names}", code)
            except Exception:
                logging.debug("unknown failure: killing child processes and exiting")
                logging.error(traceback.format_exc())
                returncode = compute_returncode(queue.cases())
                raise
            else:
                if logging.get_level() > logging.INFO:
                    queue.update_progress_bar(start, last=True)
                returncode = compute_returncode(queue.cases())
                queue.close(cleanup=cleanup_queue)
                stop = timestamp()
                dt = stop - start
                msg = colorize("@*{Finished} %d %s (%s)\n" % (queue_size, what, hhmmss(dt)))
                logging.info(msg)
                atexit.unregister(cleanup_children)
    return returncode


def setup_queue(cases: list[TestCase], fail_fast: bool = False) -> ResourceQueue:
    """Setup the test queue

    Args:
        cases: the test cases to run

    """
    from _canary.queues import factory as q_factory

    kwds: dict[str, Any] = {}
    queue: ResourceQueue = q_factory(global_session_lock, fail_fast=fail_fast)
    for case in cases:
        if case.status == "skipped":
            case.save()
        elif not case.status.satisfies(("ready", "pending")):
            raise ValueError(f"{case}: case is not ready or pending")
        # elif case.work_tree is None:
        #    raise ValueError(f"{case}: exec root is not set")
    queue.put(*[case for case in cases if case.status.satisfies(("ready", "pending"))])
    queue.prepare(**kwds)
    if queue.empty():
        raise ValueError("There are no cases to run in this session")
    return queue


def process_queue(*, queue: ResourceQueue) -> None:
    """Process the test queue, asynchronously

    Args:
        queue: the test queue to process

    """
    from _canary.runners import factory as r_factory

    futures: dict = {}
    start = timestamp()
    duration = lambda: timestamp() - start
    timeout = float(config.getoption("session_timeout", -1))
    runner = r_factory()
    qsize = queue.qsize
    qrank = 0
    ppe = None
    try:
        with io.StringIO() as fh:
            config.snapshot(fh, pretty_print=False)
            os.environ["CANARYCFG64"] = compress64(fh.getvalue())
        context = multiprocessing.get_context(config.multiprocessing_context)
        with ProcessPoolExecutor(mp_context=context, max_workers=queue.workers) as ppe:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                key = keyboard.get_key()
                if isinstance(key, str) and key in "sS":
                    logging.emit(queue.status(start=start))
                if logging.get_level() > logging.INFO:
                    queue.update_progress_bar(start)
                if timeout >= 0.0 and duration() > timeout:
                    raise TimeoutError(f"Test execution exceeded time out of {timeout} s.")
                try:
                    iid, obj = queue.get()
                    heartbeat(queue)
                except BusyQueue:
                    time.sleep(0.01)
                    continue
                except EmptyQueue:
                    break
                logging.debug(f"Submitting {obj} to process pool for execution", end="... ")
                future = ppe.submit(runner, obj, qsize=qsize, qrank=qrank)
                qrank += 1
                callback = partial(done_callback, iid, queue)
                future.add_done_callback(callback)
                logging.log(logging.DEBUG, "done")
                futures[iid] = (obj, future)
    except BaseException:
        if ppe is None:
            raise ProcessPoolExecutorFailedToStart
        raise
    finally:
        if ppe is not None:
            ppe.shutdown(cancel_futures=True)


def done_callback(iid: int, queue: ResourceQueue, future: Future) -> None:
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
        future.result()
    except BrokenProcessPool:
        # The future was probably killed by fail_fast or a keyboard interrupt
        return
    except BrokenPipeError:
        # something bad happened.  On some HPCs we have seen:
        # BrokenPipeError: [Errno 108] Cannot send after transport endpoint shutdown
        # Seems to be a filesystem issue, punt for now
        return

    # The case (or batch) was run in a subprocess.  The object must be
    # refreshed so that the state in this main thread is up to date.

    obj: TestCase | TestBatch = queue.done(iid)
    if not isinstance(obj, (TestBatch, TestCase)):
        logging.error(f"Expected AbstractTestCase, got {obj.__class__.__name__}")
        return
    obj.refresh()
    logging.debug(f"Finished {obj} ({obj.duration} s.)")
    if not isinstance(obj, TestCase):
        assert isinstance(obj, TestBatch)
        if all(case.status == "retry" for case in obj):
            queue.retry(iid)
            return
        for case in obj:
            if case.status == "running":
                # Job was cancelled
                case.status.set("cancelled", "batch cancelled")
            elif case.status == "skipped":
                pass
            elif case.status == "ready":
                case.status.set("not_run", "test not run for unknown reasons")
            elif case.start > 0 and case.stop < 0:
                case.status.set("cancelled", "test case cancelled")


def heartbeat(queue: ResourceQueue) -> None:
    """Take a heartbeat of the simulation by dumping the case, cpu, and gpu IDs that are
    currently busy

    """
    if not config.debug:
        return None
    if isinstance(queue, BatchResourceQueue):
        return None
    assert config.session.work_tree is not None
    log_dir = os.path.join(config.session.work_tree, ".canary/logs")
    hb: dict[str, Any] = {"date": datetime.now().strftime("%c")}
    busy = queue.busy()
    hb["busy"] = [case.id for case in busy]
    hb["busy cpus"] = [cpu_id for case in busy for cpu_id in case.cpu_ids]
    hb["busy gpus"] = [gpu_id for case in busy for gpu_id in case.gpu_ids]
    file: str
    if "CANARY_BATCH_ID" in os.environ:
        batch_id = os.environ["CANARY_BATCH_ID"]
        file = os.path.join(log_dir, f"hb.{batch_id}.json")
    else:
        file = os.path.join(log_dir, "hb.json")
    mkdirp(os.path.dirname(file))
    with open(file, "a") as fh:
        fh.write(json.dumps(hb) + "\n")
    return None


@contextmanager
def rc_environ(**variables) -> Generator[None, None, None]:
    """Set the runtime environment"""
    save_env = os.environ.copy()
    os.environ.update(variables)
    level = logging.get_level()
    os.environ["CANARY_LOG_LEVEL"] = logging.get_level_name(level)
    yield
    os.environ.clear()
    os.environ.update(save_env)


class ProcessPoolExecutorFailedToStart(Exception):
    pass
