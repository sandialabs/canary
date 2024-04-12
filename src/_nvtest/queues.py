import os
import sys
import time
from typing import Any
from typing import Union

from .test.partition import Partition
from .test.testcase import TestCase
from .util import keyboard
from .util.color import clen
from .util.color import colorize


class ResourceQueue:
    def __init__(self, cpus: int, devices: int, workers: int) -> None:
        self.cpus = cpus
        self.workers = workers
        self.devices = devices

        self._buffer: dict[int, Any] = {}
        self._busy: dict[int, Any] = {}
        self._finished: dict[int, Any] = {}

        self.allow_kb = os.getenv("NVTEST_DISABLE_KB") is None

    def done(self, Any) -> Any:
        raise NotImplementedError()

    def cases(self) -> list[TestCase]:
        raise NotImplementedError()

    def queued(self) -> list[Any]:
        raise NotImplementedError

    def busy(self) -> list[Any]:
        raise NotImplementedError

    def finished(self) -> list[Any]:
        raise NotImplementedError

    def empty(self) -> bool:
        return len(self._buffer) == 0

    def orphaned(self, obj_id: int) -> None:
        raise NotImplementedError

    def available_workers(self):
        return self.workers - len(self._busy)

    def available_cpus(self):
        return self.cpus - sum(obj.processors for obj in self._busy.values())

    def available_devices(self):
        return self.devices - sum(obj.devices for obj in self._busy.values())

    def available_resources(self):
        return (self.available_cpus(), self.available_devices())

    @property
    def qsize(self):
        return len(self._buffer)

    def put(self, *objs: Any) -> None:
        for obj in objs:
            self._buffer[len(self._buffer)] = obj

    def get(self) -> tuple[int, Union[TestCase, Partition]]:
        while True:
            if not len(self._buffer):
                raise Empty
            for i in list(self._buffer.keys()):
                if self.allow_kb:
                    key = keyboard.get_key()
                    if isinstance(key, str) and key in "sS":
                        self.print_status()
                obj = self._buffer[i]
                ready_flag = obj.ready()
                if ready_flag < 0:
                    # job is orphaned and will never be ready
                    self.orphaned(i)
                    continue
                elif self.available_workers() and ready_flag:
                    if (obj.processors, obj.devices) <= self.available_resources():
                        self._busy[i] = self._buffer.pop(i)
                        return (i, self._busy[i])
            time.sleep(0.0001)

    def print_status(self):
        def count(objs) -> int:
            return sum([1 if isinstance(obj, TestCase) else len(obj) for obj in objs])

        p = d = f = t = 0
        done = count(self._finished.values())
        busy = count(self._busy.values())
        notrun = count(self._buffer.values())
        total = done + busy + notrun
        for case in self.finished():
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
        text = colorize(fmt % (busy, total, done, total, notrun, total, p, d, f, t))
        n = clen(text)
        header = colorize("@*c{%s}" % " status ".center(n + 10, "="))
        footer = colorize("@*c{%s}" % "=" * (n + 10))
        pad = colorize("@*c{====}")
        sys.stdout.write(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")
        sys.stdout.flush()


class DirectResourceQueue(ResourceQueue):
    def put(self, *objs: TestCase) -> None:
        for obj in objs:
            if obj.processors > self.cpus:
                raise ValueError(
                    f"{obj!r}: required cpus ({obj.processors}) "
                    f"exceeds max cpu count ({self.cpus})"
                )
            super().put(obj)

    def orphaned(self, obj_no: int) -> None:
        self._finished[obj_no] = self._buffer.pop(obj_no)
        self._finished[obj_no].status.set("skipped", "failed dependencies")
        for case in self._buffer.values():
            for i, dep in enumerate(case.dependencies):
                if dep.id == self._finished[obj_no].id:
                    case.dependencies[i] = self._finished[obj_no]

    def done(self, obj_no: int) -> "TestCase":
        if obj_no not in self._busy:
            raise RuntimeError(f"case {obj_no} is not running")
        self._finished[obj_no] = self._busy.pop(obj_no)
        for case in self._buffer.values():
            for i, dep in enumerate(case.dependencies):
                if dep.id == self._finished[obj_no].id:
                    case.dependencies[i] = self._finished[obj_no]
        return self._finished[obj_no]

    def cases(self) -> list[TestCase]:
        return self.queued() + self.busy() + self.finished()

    def queued(self) -> list[TestCase]:
        return list(self._buffer.values())

    def busy(self) -> list[TestCase]:
        return list(self._busy.values())

    def finished(self) -> list[TestCase]:
        return list(self._finished.values())


class BatchResourceQueue(ResourceQueue):
    def put(self, *objs: Partition) -> None:
        for obj in objs:
            if obj.processors > self.cpus:
                raise ValueError(
                    f"{obj!r}: required cpus ({obj.processors}) "
                    f"exceeds max cpu count ({self.cpus})"
                )
            super().put(obj)

    def done(self, obj_no: int) -> Partition:
        if obj_no not in self._busy:
            raise RuntimeError(f"batch {obj_no} is not running")
        self._finished[obj_no] = self._busy.pop(obj_no)
        completed = dict([(_.id, _) for _ in self.finished()])
        for batch in self._buffer.values():
            for case in batch:
                for i, dep in enumerate(case.dependencies):
                    if dep.id in completed:
                        case.dependencies[i] = completed[dep.id]
        return self._finished[obj_no]

    def cases(self) -> list[TestCase]:
        cases: list[TestCase] = []
        for batch in self._buffer.values():
            cases.extend(batch)
        for batch in self._busy.values():
            cases.extend(batch)
        for batch in self._finished.values():
            cases.extend(batch)
        return cases

    def queued(self) -> list[Partition]:
        return list(self._buffer.values())

    def busy(self) -> list[Partition]:
        return list(self._busy.values())

    def finished(self) -> list[Partition]:
        return list(self._finished.values())


class Empty(Exception):
    pass
