import glob
import io
import json
import os
import threading
import time
from typing import Any
from typing import Optional
from typing import Union

from .test.batch import Batch
from .test.batch import factory as b_factory
from .test.case import TestCase
from .third_party import color
from .util import logging
from .util.filesystem import mkdirp
from .util.partition import partition_n
from .util.partition import partition_t
from .util.progress import progress
from .util.resource import BatchInfo
from .util.resource import ResourceInfo


class ResourceQueue:
    def __init__(self, resourceinfo: ResourceInfo, lock: threading.Lock) -> None:
        self.cpus = int(resourceinfo["session:cpus"])
        self.devices = int(resourceinfo["session:devices"])
        self.workers = int(resourceinfo["session:workers"])

        self._buffer: dict[int, Any] = {}
        self._busy: dict[int, Any] = {}
        self._finished: dict[int, Any] = {}
        self.lock = lock

    def mark_done(self, Any) -> Any:
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

    def _skipped(self, obj_id: int) -> None:
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

    def prepare(self) -> None:
        pass

    def get(self) -> Optional[tuple[int, Union[TestCase, Batch]]]:
        with self.lock:
            if not self.available_workers():
                return None
            if not len(self._buffer):
                raise Empty
            for i in list(self._buffer.keys()):
                obj = self._buffer[i]
                status = obj.status
                if status == "skipped":
                    # job is skipped and will never be ready
                    self._skipped(i)
                    continue
                elif status == "ready":
                    if (obj.processors, obj.devices) <= self.available_resources():
                        self._busy[i] = self._buffer.pop(i)
                        return (i, self._busy[i])
        return None

    def status(self) -> str:
        def count(objs) -> int:
            return sum([1 if isinstance(obj, TestCase) else len(obj) for obj in objs])

        string = io.StringIO()
        with self.lock:
            p = d = f = t = 0
            done = count(self.finished())
            busy = count(self.busy())
            notrun = count(self.queued())
            total = done + busy + notrun
            for obj in self.finished():
                if isinstance(obj, TestCase):
                    obj = [obj]
                for case in obj:
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
            text = color.colorize(fmt % (busy, total, done, total, notrun, total, p, d, f, t))
            n = color.clen(text)
            header = color.colorize("@*c{%s}" % " status ".center(n + 10, "="))
            footer = color.colorize("@*c{%s}" % "=" * (n + 10))
            pad = color.colorize("@*c{====}")
            string.write(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")
        return string.getvalue()

    def display_progress(self, start: float, last: bool = False) -> None:
        with self.lock:
            progress(self.cases(), time.monotonic() - start)
            if last:
                logging.emit("\n")


class DirectResourceQueue(ResourceQueue):
    def put(self, *objs: TestCase) -> None:
        for obj in objs:
            if obj.processors > self.cpus:
                raise ValueError(
                    f"{obj!r}: required cpus ({obj.processors}) "
                    f"exceeds max cpu count ({self.cpus})"
                )
            super().put(obj)

    def _skipped(self, obj_no: int) -> None:
        self._finished[obj_no] = self._buffer.pop(obj_no)
        for case in self._buffer.values():
            for i, dep in enumerate(case.dependencies):
                if dep.id == self._finished[obj_no].id:
                    case.dependencies[i] = self._finished[obj_no]

    def mark_done(self, obj_no: int) -> "TestCase":
        with self.lock:
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
    store = "B"
    index_file = "index"

    def __init__(
        self, resourceinfo: ResourceInfo, batchinfo: BatchInfo, lock: threading.Lock
    ) -> None:
        super().__init__(resourceinfo, lock)
        self.batchinfo = batchinfo
        scheduler = self.batchinfo.scheduler
        if scheduler is None:
            raise ValueError("BatchResourceQueue requires a scheduler")
        elif scheduler not in ("slurm", "shell"):
            raise ValueError(f"{scheduler}: unknown scheduler")
        self.scheduler: str = str(scheduler)
        self.tmp_buffer: list[TestCase] = []

    def prepare(self) -> None:
        root = self.tmp_buffer[0].exec_root
        assert root is not None
        batch_store = os.path.join(root, ".nvtest", self.store)
        batch_stores = glob.glob(os.path.join(batch_store, "*"))
        partitions: list[set[TestCase]]
        if self.batchinfo.count:
            count = self.batchinfo.count
            partitions = partition_n(self.tmp_buffer, n=count)
        else:
            limit = float(self.batchinfo.limit or 30 * 60)  # 30 minute default
            partitions = partition_t(self.tmp_buffer, t=limit)
        n = len(partitions)
        N = len(batch_stores) + 1
        batches = [
            b_factory(p, i, n, N, scheduler=self.scheduler, avail_workers=self.workers)
            for i, p in enumerate(partitions, start=1)
            if len(p)
        ]
        for batch in batches:
            batch.setup(*self.batchinfo.args)
        for batch in batches:
            super().put(batch)
        fd: dict[int, list[str]] = {}
        for batch in batches:
            cases = fd.setdefault(batch.world_rank, [])
            cases.extend([case.id for case in batch])
        batch_dir = os.path.join(batch_store, str(N))
        file = os.path.join(batch_dir, self.index_file)
        mkdirp(os.path.dirname(file))
        with open(file, "w") as fh:
            json.dump({"index": fd}, fh, indent=2)
        file = os.path.join(batch_dir, "meta.json")
        with open(file, "w") as fh:
            json.dump({"meta": vars(self.batchinfo)}, fh, indent=2)

    def put(self, *objs: TestCase) -> None:
        for obj in objs:
            if obj.processors > self.cpus:
                raise ValueError(
                    f"{obj!r}: required cpus ({obj.processors}) "
                    f"exceeds max cpu count ({self.cpus})"
                )
            self.tmp_buffer.append(obj)

    def _skipped(self, obj_no: int) -> None:
        self._finished[obj_no] = self._buffer.pop(obj_no)
        finished = {case.id: case for case in self._finished[obj_no]}
        for batch in self._buffer.values():
            for case in batch:
                for i, dep in enumerate(case.dependencies):
                    if dep.id in finished:
                        case.dependencies[i] = finished[dep.id]

    def mark_done(self, obj_no: int) -> Batch:
        with self.lock:
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
        cases.extend([case for batch in self._buffer.values() for case in batch])
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        return cases

    def queued(self) -> list[Batch]:
        return list(self._buffer.values())

    def busy(self) -> list[Batch]:
        return list(self._busy.values())

    def finished(self) -> list[Batch]:
        return list(self._finished.values())


class Empty(Exception):
    pass
