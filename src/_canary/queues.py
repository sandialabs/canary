# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import abc
import io
import math
import threading
import time
from typing import Any
from typing import Callable

from . import config
from .error import FailFast
from .test.batch import TestBatch
from .test.case import TestCase
from .third_party import color
from .util import logging
from .util.progress import progress
from .util.rprobe import cpu_count
from .util.time import hhmmss
from .util.time import timestamp


class ResourceQueue(abc.ABC):
    def __init__(self, *, lock: threading.Lock, workers: int) -> None:
        self.fail_fast = False
        self.workers = workers
        self.buffer: dict[int, Any] = {}
        self._busy: dict[int, Any] = {}
        self._finished: dict[int, Any] = {}
        self._notrun: dict[int, Any] = {}
        self.meta: dict[int, dict] = {}
        self.lock = lock
        self.exclusive_lock: bool = False

    def __len__(self) -> int:
        return len(self.buffer)

    @abc.abstractmethod
    def iter_keys(self) -> list[int]: ...

    @abc.abstractmethod
    def done(self, obj_id: int) -> Any: ...

    @abc.abstractmethod
    def retry(self, obj_id: int) -> Any: ...

    @abc.abstractmethod
    def cases(self) -> list[TestCase]: ...

    @abc.abstractmethod
    def queued(self) -> list[Any]: ...

    @abc.abstractmethod
    def busy(self) -> list[Any]: ...

    @abc.abstractmethod
    def finished(self) -> list[Any]: ...

    @abc.abstractmethod
    def notrun(self) -> list[Any]: ...

    @abc.abstractmethod
    def failed(self) -> list[TestCase]: ...

    def empty(self) -> bool:
        return len(self.buffer) == 0

    @abc.abstractmethod
    def skip(self, obj_id: int) -> None: ...

    def available_workers(self) -> int:
        return self.workers - len(self._busy)

    @property
    def qsize(self):
        return len(self.buffer)

    def put(self, *cases: Any) -> None:
        for case in cases:
            self.buffer[len(self.buffer)] = case

    def prepare(self, **kwds: Any) -> None:
        pass

    def close(self, cleanup: bool = True) -> None:
        if cleanup:
            for case in self.cases():
                if case.status == "running":
                    case.status.set("cancelled", "Case failed to stop")
                    case.save()
                elif case.status.value in ("retry", "created", "pending", "ready"):
                    case.status.set("not_run", "Case failed to start")
                    case.save()
        keys = list(self.buffer.keys())
        for key in keys:
            self._notrun[key] = self.buffer.pop(key)

    def get(self) -> tuple[int, TestCase | TestBatch]:
        """return (total number in queue, this number, iid, obj)"""
        if self.fail_fast and (failed := self.failed()):
            raise FailFast(failed=failed)
        with self.lock:
            if self.available_workers() <= 0:
                raise Busy
            if not len(self.buffer):
                raise Empty
            for i in self.iter_keys():
                obj = self.buffer[i]
                status = obj.status
                if status.value not in ("retry", "pending", "ready", "running"):
                    # job will never be ready
                    self.skip(i)
                    continue
                elif status == "ready":
                    try:
                        if obj.exclusive and self.busy():
                            continue
                        required = obj.required_resources()
                        if not required:
                            raise ValueError(f"{obj}: a test should require at least 1 cpu")
                        acquired = config.resource_pool.acquire(required)
                        obj.assign_resources(acquired)
                    except config.ResourceUnavailable:
                        continue
                    else:
                        self._busy[i] = self.buffer.pop(i)
                        if obj.exclusive:
                            self.exclusive_lock = True
                        return (i, self._busy[i])
        raise Busy

    def counts(self, count: Callable = len) -> tuple[int, int, int]:
        done = count(self.finished())
        busy = count(self.busy())
        notrun = count(self.queued())
        notrun += count(self.notrun())
        return done, busy, notrun

    def status(self, start: float | None = None) -> str:
        def count(objs) -> int:
            return sum([1 if isinstance(obj, TestCase) else len(obj) for obj in objs])

        string = io.StringIO()
        with self.lock:
            p = d = f = t = 0
            done, busy, notrun = self.counts(count=count)
            total = done + busy + notrun
            for obj in self.finished():
                if isinstance(obj, TestCase):
                    obj = [obj]
                for case in obj:
                    if case.status.value in ("success", "xdiff", "xfail"):
                        p += 1
                    elif case.status == "diffed":
                        d += 1
                    elif case.status == "timeout":
                        t += 1
                    else:
                        f += 1
            fmt = "%d/%d running, %d/%d done, %d/%d queued "
            if start is not None:
                duration = hhmmss(time.time() - start)
                fmt += f"in {duration} "
            fmt += "(@g{%d pass}, @y{%d diff}, @r{%d fail}, @m{%d timeout})"
            text = color.colorize(fmt % (busy, total, done, total, notrun, total, p, d, f, t))
            n = color.clen(text)
            header = color.colorize("@*c{%s}" % " status ".center(n + 10, "="))
            footer = color.colorize("@*c{%s}" % "=" * (n + 10))
            pad = color.colorize("@*c{====}")
            string.write(f"\n{header}\n{pad} {text} {pad}\n{footer}\n\n")
        return string.getvalue()

    def update_progress_bar(self, start: float, last: bool = False) -> None:
        with self.lock:
            progress(self.cases(), timestamp() - start)
            if last:
                logging.emit("\n")


class DirectResourceQueue(ResourceQueue):
    def __init__(self, lock: threading.Lock) -> None:
        workers = int(config.getoption("workers", -1))
        super().__init__(lock=lock, workers=cpu_count() if workers < 0 else workers)

    def iter_keys(self) -> list[int]:
        # want bigger tests first
        norm = lambda c: math.sqrt(c.cpus**2 + c.runtime**2)
        return sorted(self.buffer.keys(), key=lambda k: norm(self.buffer[k]), reverse=True)

    def retry(self, obj_id: int) -> Any:
        raise NotImplementedError

    def put(self, *cases: Any) -> None:
        for case in cases:
            if config.debug:
                # The case should have already been validated
                config.resource_pool.satisfiable(case.required_resources())
            super().put(case)

    def skip(self, obj_no: int) -> None:
        self._finished[obj_no] = self.buffer.pop(obj_no)
        for case in self.buffer.values():
            for i, dep in enumerate(case.dependencies):
                if dep.id == self._finished[obj_no].id:
                    case.dependencies[i] = self._finished[obj_no]

    def done(self, obj_no: int) -> "TestCase":
        with self.lock:
            if obj_no not in self._busy:
                raise RuntimeError(f"case {obj_no} is not running")
            obj = self._finished[obj_no] = self._busy.pop(obj_no)
            config.resource_pool.reclaim(obj.resources)
            obj.free_resources()
            if obj.exclusive:
                self.exclusive_lock = False
            for case in self.buffer.values():
                for i, dep in enumerate(case.dependencies):
                    if dep.id == self._finished[obj_no].id:
                        case.dependencies[i] = self._finished[obj_no]
            return self._finished[obj_no]

    def cases(self) -> list[TestCase]:
        return self.queued() + self.busy() + self.finished() + self.notrun()

    def queued(self) -> list[TestCase]:
        return list(self.buffer.values())

    def busy(self) -> list[TestCase]:
        return list(self._busy.values())

    def finished(self) -> list[TestCase]:
        return list(self._finished.values())

    def notrun(self) -> list[TestCase]:
        return list(self._notrun.values())

    def failed(self) -> list[TestCase]:
        return [_ for _ in self._finished.values() if _.status != "success"]


class BatchResourceQueue(ResourceQueue):
    def __init__(self, lock: threading.Lock) -> None:
        workers = int(config.getoption("workers", -1))
        super().__init__(lock=lock, workers=5 if workers < 0 else workers)
        if config.backend is None:
            raise ValueError("BatchResourceQueue requires a batch:scheduler")
        self.tmp_buffer: list[TestCase] = []

    def iter_keys(self) -> list[int]:
        return list(self.buffer.keys())

    def prepare(self, **kwds: Any) -> None:
        batches: list[TestBatch] | None = config.plugin_manager.hook.canary_testcases_batch(
            cases=self.tmp_buffer
        )
        if batches is None:
            raise ValueError(
                "No test batches generated (this should never happen, "
                "the default batching scheme should have been used)"
            )
        logging.info(f"Generated {len(batches)} batches")
        for batch in batches:
            super().put(batch)

    def put(self, *cases: Any) -> None:
        for case in cases:
            if config.debug:
                # The case should have already been validated
                config.resource_pool.satisfiable(case.required_resources())
            self.tmp_buffer.append(case)

    def skip(self, obj_no: int) -> None:
        self._finished[obj_no] = self.buffer.pop(obj_no)
        finished = {case.id: case for case in self._finished[obj_no]}
        for batch in self.buffer.values():
            for case in batch:
                for i, dep in enumerate(case.dependencies):
                    if dep.id in finished:
                        case.dependencies[i] = finished[dep.id]

    def done(self, obj_no: int) -> TestBatch:
        with self.lock:
            if obj_no not in self._busy:
                raise RuntimeError(f"batch {obj_no} is not running")
            obj = self._finished[obj_no] = self._busy.pop(obj_no)
            config.resource_pool.reclaim(obj.resources)
            obj.free_resources()
            completed = dict([(_.id, _) for _ in self.finished()])
            for batch in self.buffer.values():
                for case in batch:
                    for i, dep in enumerate(case.dependencies):
                        if dep.id in completed:
                            case.dependencies[i] = completed[dep.id]
            return self._finished[obj_no]

    def retry(self, obj_no: int) -> None:
        if obj_no not in self._finished:
            raise ValueError("Cannot retry a job that is not done")
        with self.lock:
            meta = self.meta.setdefault(obj_no, {})
            meta["retry"] = meta.setdefault("retry", 0) + 1
            if meta["retry"] >= 3:
                for case in self._finished[obj_no]:
                    case.status.set("failed", "Maximum number of retries exceeded")
                    case.save()
            else:
                self.buffer[obj_no] = self._finished.pop(obj_no)
                for case in self.buffer[obj_no]:
                    if case.status.value not in ("pending", "ready"):
                        if case.dependencies:
                            case.status.set("pending")
                        else:
                            case.status.set("ready")
                        case.save()

    def cases(self) -> list[TestCase]:
        cases: list[TestCase] = []
        cases.extend([case for batch in self.buffer.values() for case in batch])
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        cases.extend([case for batch in self._notrun.values() for case in batch])
        return cases

    def queued(self) -> list[TestBatch]:
        return list(self.buffer.values())

    def busy(self) -> list[TestBatch]:
        return list(self._busy.values())

    def finished(self) -> list[TestBatch]:
        return list(self._finished.values())

    def notrun(self) -> list[TestBatch]:
        return list(self._notrun.values())

    def failed(self) -> list[TestCase]:
        return [_ for batch in self._finished.values() for _ in batch if _.status != "success"]


def factory(lock: threading.Lock, fail_fast: bool = False) -> ResourceQueue:
    """Setup the test queue

    Args:
      lock: threading lock

    """
    queue: ResourceQueue
    if config.backend is None:
        queue = DirectResourceQueue(lock)
    else:
        queue = BatchResourceQueue(lock)
    queue.fail_fast = fail_fast
    return queue


class Empty(Exception):
    pass


class Busy(Exception):
    pass
