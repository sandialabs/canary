import os
import sys
import time
from io import StringIO
from typing import Any
from typing import Generator
from typing import Union

from ..test.enums import Result
from ..test.partition import Partition
from ..test.testcase import TestCase
from ..util import keyboard
from ..util.tty.color import colorize


class Queue:
    def __init__(self, cpus: int, workers: int, work_items: Any) -> None:
        self.work_items = work_items
        self.workers: int = workers or os.cpu_count() or 1
        self.cpus = cpus
        self.queue = self.create_queue(work_items)
        self._running: dict[int, Any] = {}
        self._done: dict[int, Any] = {}

    def create_queue(self, *args, **kwargs):
        raise NotImplementedError

    def refresh_queue(self, *args, **kwargs):
        raise NotImplementedError

    def batch_info(self) -> Union[list[list[str]], None]:
        return None

    def cases(self) -> list[TestCase]:
        raise NotImplementedError

    def empty(self) -> bool:
        return len(self.queue) == 0

    def get_from_running(self, case_no: int) -> Any:
        return self._running[case_no]

    def mark_as_complete(self, case_no: int, item: Any) -> None:
        my_item = self._running.pop(case_no)
        assert id(my_item) == id(item), str(item)
        self._done[case_no] = item

    def get(self, case_no: int) -> Any:
        if case_no in self.queue:
            return self.queue[case_no]
        elif case_no in self._running:
            return self._running[case_no]
        elif case_no in self._done:
            return self._done[case_no]
        raise ValueError(f"Item {case_no} not in queue")

    def pool(self) -> Generator[tuple[int, Any], None, None]:
        while True:
            i, item = self.pop_next()
            if item is None:
                break
            assert isinstance(i, int)
            self._running[i] = item
            yield i, item

    @property
    def avail_workers(self):
        busy = len(self._running)
        return self.workers - busy

    @property
    def avail_cpus(self):
        busy = sum(case.size for case in self._running.values())
        return self.cpus - busy

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
        if not len(self.queue):
            raise StopIteration
        while True:
            key = keyboard.get_key()
            if isinstance(key, str) and key in "sS":
                self.print_status()
            for (i, item) in self.queue.items():
                if self.avail_workers and item.size <= self.avail_cpus and item.ready:
                    break
            else:
                time.sleep(1)
                continue
            self._running[i] = self.queue.pop(i)
            return i, item

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
        stat = StringIO()
        fmt = "@b{===} %d/%d running, %d/%d done, %d/%d queued "
        stat.write(colorize(fmt % (running, total, done, total, notrun, total)))
        fmt = " (@g{%d pass}, @y{%d diff}, @r{%d fail}, @m{%d timeout}) @b{===}\n"
        extra = colorize(fmt % (p, f, d, t))
        stat.write(extra)
        sys.stdout.write(stat.getvalue())
