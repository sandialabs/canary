import multiprocessing as mp
import time
from typing import Any
from typing import Callable

from .queue import AbstractResourceQueue
from .queue import Busy
from .testspec import TestCase


class MeasuredProcess(mp.Process):
    pass


def process_queue(queue: AbstractResourceQueue, runner: Callable, **kwargs: Any) -> int:
    """
    Run tests in parallel using MeasuredProcess, respecting timeouts
    and collecting CPU/memory metrics. Each test receives a result_queue
    to report its status/message dict back to the parent.
    """
    processes: list[tuple[mp.Process, TestCase, float, mp.Queue]] = []
    polling_frequency = 0.5
    try:
        while queue.is_active() or processes:
            # Launch new processes up to the worker limit
            while len(processes) < queue.workers:
                try:
                    case = queue.get()
                except Busy:
                    break

                # Create a per-test Queue for runner to report status/messages
                q = mp.Queue()
                p = MeasuredProcess(target=runner, args=(case, q))
                p.start()
                processes.append((p, case, time.monotonic(), q))

            # Poll active processes
            active = []
            now = time.monotonic()
            for p, case, start_time, q in processes:
                elapsed = now - start_time

                if p.is_alive():
                    # Timeout enforcement
                    if elapsed > case.spec.timeout:
                        print(f"[{case.name}] Timeout ({elapsed:.1f}s), terminating")
                        p.terminate()
                        queue.done(case)
                    else:
                        active.append((p, case, start_time, q))
                else:
                    # Process finished normally
                    p.join()
                    queue.done(case)

                # Merge any dicts from result_queue into the test case
                while not q.empty():
                    update = q.get()
                    # Parent updates the test case copy with the received status/message
                    case.status.value = update.get("status") or "unknown"
                    case.status.details = update.get("message")
                    case.status.code = update.get("returncodecode")

            processes.clear()
            processes.extend(active)
            time.sleep(polling_frequency)

    except KeyboardInterrupt:
        print("KeyboardInterrupt detected. Terminating all active processes...")
        for p, case, _, _ in processes:
            p.terminate()
        raise
