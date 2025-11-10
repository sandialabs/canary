import multiprocessing as mp
import time
from typing import Any
from typing import Callable
import sys

from . import config
from .error import timeout_exit_status
from .queue import AbstractResourceQueue
from .queue import Busy, Empty
from .testspec import TestCase

import multiprocessing as mp
import time
from typing import Callable, Any, Dict
import logging

logger = logging.getLogger(__name__)


class MeasuredProcess(mp.Process):
    def __init__(self, *args, case, qid, queue, **kwargs):
        self.mp_case: TestCase = case
        self.mp_qid: int = qid
        self.mp_queue: mp.Queue = queue
        self.mp_start: float = 0.0
        self.mp_stop: float = 0.0
        super().__init__(*args, **kwargs)

    def start(self):
        self.mp_start = time.time()
        return super().start()

    def terminate(self):
        self.mp_stop = time.time()
        return super().terminate()

    def join(self):
        self.mp_stop = time.time()
        return super().join()


class ProcessPool:
    """
    Manages a pool of worker processes.

    Example usage:
    pool = ProcessPool(max_workers=4, queue=my_queue, runner=my_runner).run()
    """

    def __init__(self, max_workers: int, queue: AbstractResourceQueue, runner: Callable, busy_wait_time: float = 0.5):
        """
        Initialize the process pool.

        Args:
        max_workers: Maximum number of concurrent worker processes
        queue: ResourceQueue instance
        runner: Callable that processes cases
        busy_wait_time: Time to wait when queue is busy
        """
        self.max_workers = max_workers
        self.queue = queue
        self.runner = runner
        self.busy_wait_time = busy_wait_time
        self.active_processes: Dict[int, MeasuredProcess] = {}

    def clean_finished_processes(self):
        """Remove finished processes from the active dict."""
        now = time.time()
        for pid in list(self.active_processes.keys()):
            proc = self.active_processes[pid]
            if not proc.is_alive():
                proc.join()     # Clean up the process
                self.queue.done(proc.mp_qid)
                results = proc.mp_queue.get()
                proc.mp_case.update(**results)
                self.active_processes.pop(pid)
                logger.debug(f"Process {pid} finished and cleaned up")
            elif proc.mp_case.timeout < now - proc.mp_start:
                # Timeout
                proc.terminate()
                time.sleep(1)
                # Give processes time to terminate gracefully
                self.active_processes.pop(pid)
                if proc.is_alive():
                    proc.kill()
                proc.mp_case.status.set("timeout")
                self.queue.done(proc.mp_qid)

    def wait_for_slot(self):
        """Wait until a process slot is available."""
        while len(self.active_processes) >= self.max_workers:
            self.clean_finished_processes()
            if len(self.active_processes) >= self.max_workers:
                time.sleep(0.1)     # Brief sleep before checking again

    def run(self):
        """Main loop: get cases from queue and launch processes."""
        logger.info(f"Starting process pool with max {self.max_workers} workers")
        while True:
            try:
                # Clean up any finished processes
                self.clean_finished_processes()

                # Wait for a slot if at max capacity
                self.wait_for_slot()

                # Get a case from the queue
                qid, case = self.queue.get()

                # Launch a new process
                case.status.set("running")
                queue = mp.Queue()
                proc = MeasuredProcess(
                    target=self.runner,
                    args=(case, queue),
                    kwargs={"qsize": 1, "qrank": 0},
                    queue=queue,
                    qid=qid,
                    case=case,
                )
                proc.start()
                self.active_processes[proc.pid] = proc

                logger.info(
                    f"Launched process {proc.pid} for case {case}. "
                    f"Active: {len(self.active_processes)}/{self.max_workers}"
                )

            except Busy:
                # Queue is busy, wait and try again
                logger.debug(f"Queue busy, waiting {self.busy_wait_time}s")
                time.sleep(self.busy_wait_time)

            except Empty:
                # Queue is empty, wait for remaining jobs and exit
                logger.debug("Queue empty, waiting for remaining jobs to complete")
                self.wait_all()
                logger.debug("All jobs completed")
                break

            except KeyboardInterrupt:
                logger.warning("Interrupted, terminating all processes")
                self.terminate_all()
                break


    def wait_all(self):
        """Wait for all active processes to complete."""
        while self.active_processes:
            self.clean_finished_processes()
            if self.active_processes:
                time.sleep(0.1)

    def terminate_all(self):
        """Terminate all active processes."""
        for pid, proc in self.active_processes.items():
            if proc.is_alive():
                logger.warning(f"Terminating process {pid}")
                proc.terminate()

        # Give processes time to terminate gracefully
        time.sleep(1)

        # Force kill if still alive
        for pid, proc in self.active_processes.items():
            if proc.is_alive():
                logger.warning(f"Killing process {pid}")
                proc.kill()

        # Clean up
        for proc in self.active_processes.values():
            proc.join()

        self.active_processes.clear()
