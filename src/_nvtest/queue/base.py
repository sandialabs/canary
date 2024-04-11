import os
import sys
import time
from contextlib import contextmanager
from typing import Any
from typing import Generator
from typing import Optional
from typing import Union

from ..test.partition import Partition
from ..test.testcase import TestCase
from ..util import keyboard
from ..util.color import clen
from ..util.color import colorize

lock_wait_time = 0.00001


class Queue:
    def __init__(self, cpus: int, devices: int, workers: int, work_items: Any) -> None:
        self.work_items = work_items
        self.workers = workers
        self.cpus = cpus
        self.devices = devices
        self.ready: dict[int, Any] = {}
        self.busy: dict[int, Any] = {}
        self.finished: dict[int, Any] = {}
        self._lock: list[int] = []
        self.allow_kb = os.getenv("NVTEST_DISABLE_KB") is None
        self.prepared = False

    def prepare(self) -> None:
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

    def batch_info(self) -> Optional[list[list[str]]]:
        return None

    @property
    def cases(self) -> list[TestCase]:
        raise NotImplementedError

    def empty(self) -> bool:
        return len(self.ready) == 0

    def done(self, *args, **kwargs) -> Any:
        raise NotImplementedError

    def orphaned(self, *args, **kwargs) -> Any:
        raise NotImplementedError

    @property
    def _avail_workers(self):
        return self.workers - len(self.busy)

    @property
    def _avail_cpus(self):
        return self.cpus - sum(case.processors for case in self.busy.values())

    @property
    def _avail_devices(self):
        return self.devices - sum(case.devices for case in self.busy.values())

    @property
    def avail_resources(self):
        return (self._avail_cpus, self._avail_devices)

    @property
    def size(self):
        return len(self.ready)

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

    def get_ready(self) -> tuple[int, Union[TestCase, Partition]]:
        if not self.prepared:
            raise ValueError("prepare() must be called first")
        while True:
            if not len(self.ready):
                raise StopIteration
            ids = list(self.ready.keys())
            for id in ids:
                if self.allow_kb:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        self.print_status()
                    elif isinstance(key, str) and key in "kK":
                        self.kill_running()
                item = self.ready[id]
                with self.lock():
                    avail_workers = self._avail_workers
                    job_is_ready = item.ready()
                    if job_is_ready < 0:
                        # job is orphaned and will never be ready
                        self.orphaned(id)
                        continue
                    elif avail_workers and job_is_ready:
                        if (item.processors, item.devices) <= self.avail_resources:
                            self.busy[id] = self.ready.pop(id)
                            return id, item
            time.sleep(lock_wait_time)

    def print_status(self):
        p = d = f = t = 0
        done = self.cases_done
        running = self.cases_running
        notrun = self.cases_notrun
        total = done + running + notrun
        for case in self.completed_testcases():
            if case.status == "success":
                p += 1
            elif case.status == "diffed":
                d += 1
            elif case.status == "timeout":
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

    def kill_running(self):
        for case in self.cases_running:
            case.kill()
