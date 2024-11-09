import abc
import io
import threading
from typing import Any
from typing import Optional

from . import config
from .resource import ResourceHandler
from .test.batch import TestBatch
from .test.case import TestCase
from .third_party import color
from .util import logging
from .util.partition import partition_n
from .util.partition import partition_t
from .util.progress import progress
from .util.rprobe import cpu_count
from .util.time import timestamp


class ResourceQueue(abc.ABC):
    def __init__(
        self,
        *,
        lock: threading.Lock,
        workers: int,
        cpu_ids: list[int],
        gpu_ids: list[int],
    ) -> None:
        self.cpu_ids = list(cpu_ids)
        self.gpu_ids = list(gpu_ids)
        self.workers = workers
        self.buffer: dict[int, Any] = {}
        self._busy: dict[int, Any] = {}
        self._finished: dict[int, Any] = {}
        self._notrun: dict[int, Any] = {}
        self.meta: dict[int, dict] = {}
        self.lock = lock
        self.cpu_count = len(self.cpu_ids)
        self.gpu_count = len(self.gpu_ids)

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

    def empty(self) -> bool:
        return len(self.buffer) == 0

    @abc.abstractmethod
    def skip(self, obj_id: int) -> None: ...

    def available_workers(self) -> int:
        return self.workers - len(self._busy)

    def available_cpus(self) -> int:
        return len(self.cpu_ids)

    def available_gpus(self) -> int:
        return len(self.gpu_ids)

    def available_resources(self) -> tuple[int, int]:
        return (self.available_cpus(), self.available_gpus())

    def acquire_cpus(self, n: int) -> list[int]:
        N = len(self.cpu_ids)
        if N < n:
            raise ResourceError(f"requested cpus ({n}) exceeds available cpus ({N})")
        elif n:
            logging.debug(f"Acquiring {n} CPU{'s ' if n > 1 else ' '}from {N} available")
        cpu_ids = list(self.cpu_ids[:n])
        del self.cpu_ids[:n]
        return cpu_ids

    def acquire_gpus(self, n: int) -> list[int]:
        N = len(self.gpu_ids)
        if N < n:
            raise ResourceError(f"requested gpus ({n}) exceeds available gpus ({N})")
        elif n:
            logging.debug(f"Acquiring {n} GPU{'s ' if n > 1 else ' '}from {N} available")
        gpu_ids = list(self.gpu_ids[:n])
        del self.gpu_ids[:n]
        return gpu_ids

    def release_cpus(self, ids: list[int]) -> None:
        if ids:
            logging.debug(f"Releasing {len(ids)} CPU IDs ({idjoin(ids)})")
        self.cpu_ids.extend(ids)
        self.cpu_ids.sort()

    def release_gpus(self, ids: list[int]) -> None:
        if ids:
            logging.debug(f"Releasing {len(ids)} GPU IDs ({idjoin(ids)})")
        self.gpu_ids.extend(ids)
        self.gpu_ids.sort()

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

    def get(self) -> Optional[tuple[int, TestCase | TestBatch]]:
        with self.lock:
            if self.available_workers() <= 0:
                return None
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
                    if le((obj.cpus, obj.gpus), self.available_resources()):
                        self._busy[i] = self.buffer.pop(i)
                        self._busy[i].assign_cpu_ids(self.acquire_cpus(self._busy[i].cpus))
                        self._busy[i].assign_gpu_ids(self.acquire_gpus(self._busy[i].gpus))
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
            notrun += count(self.notrun())
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
            progress(self.cases(), timestamp() - start)
            if last:
                logging.emit("\n")


class DirectResourceQueue(ResourceQueue):
    def __init__(self, rh: ResourceHandler, lock: threading.Lock) -> None:
        workers = int(rh["session:workers"])
        super().__init__(
            lock=lock,
            cpu_ids=rh["session:cpu_ids"],
            gpu_ids=rh["session:gpu_ids"],
            workers=cpu_count() if workers < 0 else workers,
        )

    def iter_keys(self) -> list[int]:
        return sorted(self.buffer.keys(), key=lambda k: self.buffer[k].cpus)

    def retry(self, obj_id: int) -> Any:
        raise NotImplementedError

    def put(self, *cases: Any) -> None:
        for case in cases:
            if case.cpus > self.cpu_count:
                raise ValueError(
                    f"{case!r}: required cpus ({case.cpus}) "
                    f"exceeds max cpu count ({self.cpu_count})"
                )
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
            self._finished[obj_no] = self._busy.pop(obj_no)
            self.release_cpus(self._finished[obj_no].cpu_ids)
            self.release_gpus(self._finished[obj_no].gpu_ids)
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


class BatchResourceQueue(ResourceQueue):
    def __init__(self, rh: ResourceHandler, lock: threading.Lock) -> None:
        workers = int(rh["session:workers"])
        super().__init__(
            lock=lock,
            cpu_ids=rh["session:cpu_ids"],
            gpu_ids=rh["session:gpu_ids"],
            workers=5 if workers < 0 else workers,
        )
        self.rh = rh
        if self.rh["batch:scheduler"] is None:
            raise ValueError("BatchResourceQueue requires a batch:scheduler")
        self.tmp_buffer: list[TestCase] = []

    def iter_keys(self) -> list[int]:
        return list(self.buffer.keys())

    def prepare(self, **kwds: Any) -> None:
        lot_no = kwds.pop("lot_no")
        partitions: list[list[TestCase]]
        if self.rh["batch:count"]:
            partitions = partition_n(self.tmp_buffer, n=self.rh["batch:count"])
        else:
            default_length = config.get("batch:length") or 30 * 60
            length = float(self.rh["batch:length"] or default_length)  # 30 minute default
            partitions = partition_t(self.tmp_buffer, t=length)
        n = len(partitions)
        batches = [TestBatch(p, i, n, lot_no) for i, p in enumerate(partitions, start=1) if len(p)]
        for batch in batches:
            super().put(batch)

    def put(self, *cases: Any) -> None:
        for case in cases:
            if case.cpus > self.cpu_count:
                raise ValueError(
                    f"{case!r}: required cpus ({case.cpus}) "
                    f"exceeds max cpu count ({self.cpu_count})"
                )
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
            self._finished[obj_no] = self._busy.pop(obj_no)
            self.release_cpus(self._finished[obj_no].cpu_ids)
            self.release_gpus(self._finished[obj_no].gpu_ids)
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


def idjoin(ids: list[int], threshold: int = 4) -> str:
    if len(ids) <= threshold:
        return ",".join(str(_) for _ in ids)
    i = int(min(threshold / 2, 3))
    return idjoin(ids[:i]) + ",...," + idjoin(ids[-i:])


def le(arg1: tuple[int, ...], arg2: tuple[int, ...]) -> bool:
    if len(arg1) != len(arg2):
        raise ValueError(f"lengths of operands must be equal ({len(arg1)}, {len(arg2)})")
    return all(a <= b for a, b in zip(arg1, arg2))


def factory(rh: ResourceHandler, lock: threading.Lock) -> ResourceQueue:
    """Setup the test queue

    Args:
      cases: the test cases to run
      rh: resource handler

    """
    queue: ResourceQueue
    if rh["batch:scheduler"] is None:
        if rh["batch:count"] is not None or rh["batch:length"] is not None:
            raise ValueError("batched execution requires a batch:scheduler")
        queue = DirectResourceQueue(rh, lock)
    else:
        queue = BatchResourceQueue(rh, lock)
    return queue


class Empty(Exception):
    pass


class ResourceError(Exception):
    pass
