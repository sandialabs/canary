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
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

from . import config
from .atc import AbstractTestCase
from .resource_pool.rpool import ResourceUnavailable
from .third_party import color
from .util import cpu_count
from .util import logging
from .util.progress import progress
from .util.time import hhmmss
from .util.time import timestamp

if TYPE_CHECKING:
    from .resource_pool.rpool import ResourcePool
    from .testcase import TestCase

logger = logging.get_logger(__name__)


class AbstractResourceQueue(abc.ABC):
    def __init__(
        self, *, lock: threading.Lock, workers: int, resource_pool: "ResourcePool"
    ) -> None:
        self.workers: int = workers
        self.buffer: dict[str, Any] = {}
        self._busy: dict[str, Any] = {}
        self._finished: dict[str, Any] = {}
        self._notrun: dict[str, Any] = {}
        self.meta: dict[str, dict] = {}
        self.lock = lock
        self.exclusive_lock: bool = False
        self.resource_pool = resource_pool
        assert not self.resource_pool.empty()
        self.prepared: bool = False

    def __len__(self) -> int:
        return len(self.buffer)

    @classmethod
    @abc.abstractmethod
    def factory(
        cls, lock: threading.Lock, cases: Sequence["TestCase"], **kwds: Any
    ) -> "AbstractResourceQueue": ...

    @abc.abstractmethod
    def iter_keys(self) -> list[str]: ...

    def retry(self, obj: Any) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def cases(self) -> list["TestCase"]: ...

    @abc.abstractmethod
    def queued(self) -> list[AbstractTestCase]: ...

    @abc.abstractmethod
    def busy(self) -> list[AbstractTestCase]: ...

    @abc.abstractmethod
    def finished(self) -> list[AbstractTestCase]: ...

    @abc.abstractmethod
    def notrun(self) -> list[AbstractTestCase]: ...

    @abc.abstractmethod
    def failed(self) -> list[AbstractTestCase]: ...

    @abc.abstractmethod
    def update_pending(self, obj: AbstractTestCase) -> None: ...

    def empty(self) -> bool:
        return len(self.buffer) == 0

    @abc.abstractmethod
    def skip(self, obj: Any) -> None: ...

    @abc.abstractmethod
    def done(self, obj: Any) -> None: ...

    def available_workers(self) -> int:
        return self.workers - len(self._busy)

    def heartbeat(self) -> None:
        return None

    @property
    def qsize(self):
        return len(self.buffer)

    def put(self, *cases: AbstractTestCase) -> None:
        for case in cases:
            self.buffer[case.id] = case

    def prepare(self, **kwds: Any) -> None:
        self.prepared = True

    def is_active(self) -> bool:
        return len(self.buffer) > 0

    def close(self, cleanup: bool = True) -> None:
        if cleanup:
            for case in self.cases():
                if case.status.name == "RUNNING":
                    case.status.set("CANCELLED", "Case failed to stop")
                    case.save()
                elif case.status.name in ("RETRY", "CREATED", "PENDING", "READY"):
                    case.status.set("NOT_RUN", "Case failed to start")
                    case.save()
        keys = list(self.buffer.keys())
        for key in keys:
            self._notrun[key] = self.buffer.pop(key)

    def get(self) -> AbstractTestCase:
        """return (total number in queue, this number, iid, obj)"""
        with self.lock:
            if self.available_workers() <= 0:
                raise Busy
            if not len(self.buffer):
                raise Empty
            for id in self.iter_keys():
                obj = self.buffer[id]
                status = obj.status
                if status.name not in ("RETRY", "PENDING", "READY", "RUNNING"):
                    # job will never be ready
                    self.skip(obj)
                    continue
                elif status.name == "READY":
                    try:
                        if self.exclusive_lock:
                            continue
                        required = obj.required_resources()
                        if not required:
                            obj.status.set("ERROR", "a test should require at least 1 cpu")
                            self.skip(obj)
                        elif not self.resource_pool.accommodates(required):
                            obj.status.set(
                                "ERROR", "resource for this job cannot be satisfied at run time"
                            )
                            self.skip(obj)
                        acquired = self.resource_pool.checkout(required, timeout=obj.timeout)
                        obj.assign_resources(acquired)
                    except ResourceUnavailable:
                        continue
                    else:
                        self._busy[obj.id] = self.buffer.pop(obj.id)
                        if obj.exclusive:
                            self.exclusive_lock = True
                        return self._busy[id]
        raise Busy

    @abc.abstractmethod
    def status(self, start: float | None = None) -> str: ...

    def update_progress_bar(self, start: float, last: bool = False) -> None:
        with self.lock:
            progress(self.cases(), timestamp() - start)
            if last:
                logger.log(logging.EMIT, "\n", extra={"prefix": ""})


class ResourceQueue(AbstractResourceQueue):
    def __init__(self, *, lock: threading.Lock, resource_pool: "ResourcePool") -> None:
        workers = int(config.getoption("workers", -1))
        if workers < 0:
            workers = min(cpu_count(logical=False), 50)
        super().__init__(lock=lock, workers=workers, resource_pool=resource_pool)

    @classmethod
    def factory(
        cls,
        lock: threading.Lock,
        cases: Sequence["TestCase"],
        resource_pool: "ResourcePool",
        **kwds: Any,
    ) -> "ResourceQueue":
        self = ResourceQueue(lock=lock, resource_pool=resource_pool)
        for case in cases:
            if case.status.name == "SKIPPED":
                case.save()
            elif case.status.name not in ("READY", "PENDING"):
                raise ValueError(f"{case}: case is not ready or pending")
        self.put(*[case for case in cases if case.status.name in ("READY", "PENDING")])
        self.prepare()
        if self.empty():
            raise ValueError("There are no cases to run in this session")
        return self

    def iter_keys(self) -> list[str]:
        # want bigger tests first
        norm = lambda c: math.sqrt(c.cpus**2 + c.runtime**2)
        return sorted(self.buffer.keys(), key=lambda k: norm(self.buffer[k]), reverse=True)

    def put(self, *cases: Any) -> None:
        for case in cases:
            if config.get("config:debug"):
                # The case should have already been validated
                check = config.pluginmanager.hook.canary_resource_pool_accommodates(case=case)
                if not check:
                    raise ValueError(
                        f"Unable to run {case} for the the following reason: {check.reason}"
                    )
            super().put(case)

    def skip(self, obj: Any) -> None:
        self._finished[obj.id] = self.buffer.pop(obj.id)
        self._finished[obj.id].save()
        for case in self.buffer.values():
            for i, dep in enumerate(case.dependencies):
                if dep.id == self._finished[obj.id].id:
                    case.dependencies[i] = self._finished[obj.id]

    def update_pending(self, obj: "TestCase") -> None:
        for pending in self.buffer.values():
            for i, dep in enumerate(pending.dependencies):
                if dep.id == obj.id:
                    pending.dependencies[i] = obj

    def done(self, obj: Any) -> None:
        with self.lock:
            if obj.id not in self._busy:
                raise RuntimeError(f"job {obj} is not running")
            self._finished[obj.id] = self._busy.pop(obj.id)
            if obj.exclusive:
                self.exclusive_lock = False
            self.resource_pool.checkin(obj.free_resources())
            self.update_pending(obj)
            return

    def cases(self) -> list["TestCase"]:
        return self.queued() + self.busy() + self.finished() + self.notrun()

    def queued(self) -> list["TestCase"]:
        return list(self.buffer.values())

    def busy(self) -> list["TestCase"]:
        return list(self._busy.values())

    def finished(self) -> list["TestCase"]:
        return list(self._finished.values())

    def notrun(self) -> list["TestCase"]:
        return list(self._notrun.values())

    def failed(self) -> list["TestCase"]:
        return [_ for _ in self._finished.values() if _.status.name != "SUCCESS"]

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
                if case.status.name in ("SUCCESS", "XDIFF", "XFAIL"):
                    p += 1
                elif case.status.name == "DIFFED":
                    d += 1
                elif case.status.name == "TIMEOUT":
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
        hb: dict[str, Any] = {"date": datetime.now().strftime("%c")}
        busy = self.busy()
        hb["busy"] = [case.id for case in busy]
        hb["busy cpus"] = [cpu_id for case in busy for cpu_id in case.cpu_ids]
        hb["busy gpus"] = [gpu_id for case in busy for gpu_id in case.gpu_ids]
        text = json.dumps(hb)
        logger.log(logging.TRACE, f"Hearbeat: {text}")
        return None


class Empty(Exception):
    pass


class Busy(Exception):
    pass
