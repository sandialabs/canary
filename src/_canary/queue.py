# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import abc
import io
import json
import math
import threading
import time
from datetime import datetime
from typing import Any
from typing import Sequence

from . import config
from .atc import AbstractTestCase
from .error import FailFast
from .testcase import TestCase
from .third_party import color
from .util import logging
from .util.progress import progress
from .util.rprobe import cpu_count
from .util.time import hhmmss
from .util.time import timestamp

logger = logging.get_logger(__name__)


class AbstractResourceQueue(abc.ABC):
    def __init__(self, *, lock: threading.Lock, workers: int) -> None:
        self.workers: int = workers
        self.fail_fast: bool = config.getoption("fail_fast") or False
        self.buffer: dict[int, Any] = {}
        self._busy: dict[int, Any] = {}
        self._finished: dict[int, Any] = {}
        self._notrun: dict[int, Any] = {}
        self.meta: dict[int, dict] = {}
        self.lock = lock
        self.exclusive_lock: bool = False

    def __len__(self) -> int:
        return len(self.buffer)

    @classmethod
    @abc.abstractmethod
    def factory(
        cls, lock: threading.Lock, cases: Sequence[TestCase], **kwds: Any
    ) -> "AbstractResourceQueue": ...

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

    def heartbeat(self) -> None:
        return None

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

    def get(self) -> tuple[int, AbstractTestCase]:
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

    @abc.abstractmethod
    def status(self, start: float | None = None) -> str: ...

    def update_progress_bar(self, start: float, last: bool = False) -> None:
        with self.lock:
            progress(self.cases(), timestamp() - start)
            if last:
                logger.info(logging.EMIT, "\n", extra={"prefix": ""})


class ResourceQueue(AbstractResourceQueue):
    def __init__(self, lock: threading.Lock) -> None:
        workers = int(config.getoption("workers", -1))
        super().__init__(lock=lock, workers=cpu_count() if workers < 0 else workers)

    @classmethod
    def factory(
        cls, lock: threading.Lock, cases: Sequence[TestCase], **kwds: Any
    ) -> "ResourceQueue":
        self = ResourceQueue(lock=lock)
        for case in cases:
            if case.status == "skipped":
                case.save()
            elif not case.status.satisfies(("ready", "pending")):
                raise ValueError(f"{case}: case is not ready or pending")
        self.put(*[case for case in cases if case.status.satisfies(("ready", "pending"))])
        self.prepare()
        if self.empty():
            raise ValueError("There are no cases to run in this session")
        return self

    def iter_keys(self) -> list[int]:
        # want bigger tests first
        norm = lambda c: math.sqrt(c.cpus**2 + c.runtime**2)
        return sorted(self.buffer.keys(), key=lambda k: norm(self.buffer[k]), reverse=True)

    def retry(self, obj_id: int) -> Any:
        raise NotImplementedError

    def put(self, *cases: Any) -> None:
        for case in cases:
            if config.get("config:debug"):
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

    def _counts(self) -> tuple[int, int, int]:
        done = len(self.finished())
        busy = len(self.busy())
        notrun = len(self.queued())
        notrun += len(self.notrun())
        return done, busy, notrun

    def status(self, start: float | None = None) -> str:
        string = io.StringIO()
        with self.lock:
            p = d = f = t = 0
            done, busy, notrun = self._counts()
            total = done + busy + notrun
            for case in self.finished():
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

    def heartbeat(self) -> None:
        """Take a heartbeat of the simulation by dumping the case, cpu, and gpu IDs that are
        currently busy

        """
        if not config.get("config:debug"):
            return None
        assert config.get("session:work_tree") is not None
        hb: dict[str, Any] = {"date": datetime.now().strftime("%c")}
        busy = self.busy()
        hb["busy"] = [case.id for case in busy]
        hb["busy cpus"] = [cpu_id for case in busy for cpu_id in case.cpu_ids]
        hb["busy gpus"] = [gpu_id for case in busy for gpu_id in case.gpu_ids]
        text = json.dumps(hb)
        logger.debug(f"Hearbeat: {text}")
        return None


class Empty(Exception):
    pass


class Busy(Exception):
    pass
