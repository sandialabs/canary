import sys
import time
from contextlib import contextmanager
from typing import Any
from typing import Generator
from typing import Optional
from typing import Union

from ..test.enums import Result
from ..test.partition import Partition
from ..test.testcase import TestCase

# from ..util import keyboard
from ..util import rprobe
from ..util.tty.color import clen
from ..util.tty.color import colorize

lock_wait_time = 0.00001


class Queue:
    def __init__(self, cpus: int, workers: int, work_items: Any) -> None:
        self.work_items = work_items
        self.workers: int = workers or rprobe.cpu_count() or 1
        self.cpus = cpus
        self.validate()
        self.queue = self.create_queue(work_items)
        self._running: dict[int, Any] = {}
        self._done: dict[int, Any] = {}
        self._lock: list[int] = []

    def validate(self) -> None:
        raise NotImplementedError

    @contextmanager
    def lock(self) -> Generator[None, None, None]:
        lock = self.acquire_lock()
        yield
        self.release_lock(lock)

    def acquire_lock(self) -> int:
        while True:
            if not self._lock:
                self._lock.append(0)
                return self._lock[-1]
            time.sleep(lock_wait_time)

    def release_lock(self, lock_id) -> None:
        assert lock_id == 0 and lock_id in self._lock
        self._lock.pop(0)

    def locked(self) -> bool:
        return bool(len(self._lock))

    def create_queue(self, *args, **kwargs):
        raise NotImplementedError

    def batch_info(self) -> Optional[list[list[str]]]:
        return None

    @property
    def cases(self) -> list[TestCase]:
        raise NotImplementedError

    def empty(self) -> bool:
        return len(self.queue) == 0

    def mark_as_complete(self, *args, **kwargs) -> Any:
        raise NotImplementedError

    @property
    def _avail_workers(self):
        return self.workers - len(self._running)

    @property
    def _avail_cpus(self):
        return self.cpus - sum(case.size for case in self._running.values())

    @property
    def size(self):
        return len(self.queue)

    @property
    def cases_done(self) -> int:
        raise NotImplementedError

    @property
    def cases_running(self) -> int:
        raise NotImplementedError

    @property
    def cases_notrun(self) -> int:
        raise NotImplementedError

    def completed_testcases(self) -> Generator[TestCase, None, None]:
        raise NotImplementedError

    def update(self, *args) -> None:
        raise NotImplementedError

    def pop_next(self) -> tuple[int, Union[TestCase, Partition]]:
        while True:
            if not len(self.queue):
                raise StopIteration
            for i, item in self.queue.items():
                # key = keyboard.get_key()
                # if isinstance(key, str) and key in "sS":
                #    self.print_status()
                with self.lock():
                    avail_workers = self._avail_workers
                    if avail_workers and item.size <= self._avail_cpus and item.ready:
                        self._running[i] = self.queue.pop(i)
                        return i, item
            time.sleep(lock_wait_time)

    def print_status(self):
        p = d = f = t = 0
        done = self.cases_done
        running = self.cases_running
        notrun = self.cases_notrun
        total = done + running + notrun
        for case in self.completed_testcases():
            if case.result == Result.PASS:
                p += 1
            elif case.result == Result.DIFF:
                d += 1
            elif case.result == Result.TIMEOUT:
                t += 1
            else:
                f += 1
        fmt = "%d/%d running, %d/%d done, %d/%d queued "
        fmt += "(@g{%d pass}, @y{%d diff}, @r{%d fail}, @m{%d timeout})"
        text = colorize(fmt % (running, total, done, total, notrun, total, p, d, f, t))
        n = clen(text)
        header = colorize("@*c{%s}" % " status ".center(n + 10, "="))
        footer = colorize("@*c{%s}" % "=" * (n + 10))
        pad = colorize("@*c{====}")
        sys.stdout.write(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")
        sys.stdout.flush()
