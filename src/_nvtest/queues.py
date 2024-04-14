from typing import Any
from typing import Optional
from typing import Union

from .test.partition import Partition
from .test.testcase import TestCase


class ResourceQueue:
    def __init__(self, cpus: int, devices: int, workers: int) -> None:
        self.cpus = cpus
        self.workers = workers
        self.devices = devices

        self._buffer: dict[int, Any] = {}
        self._busy: dict[int, Any] = {}
        self._finished: dict[int, Any] = {}

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

    def get(self) -> Optional[tuple[int, Union[TestCase, Partition]]]:
        if not len(self._buffer):
            raise Empty
        for i in list(self._buffer.keys()):
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
        return None


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
        cases.extend([case for batch in self._buffer.values() for case in batch])
        cases.extend([case for batch in self._busy.values() for case in batch])
        cases.extend([case for batch in self._finished.values() for case in batch])
        return cases

    def queued(self) -> list[Partition]:
        return list(self._buffer.values())

    def busy(self) -> list[Partition]:
        return list(self._busy.values())

    def finished(self) -> list[Partition]:
        return list(self._finished.values())


class Empty(Exception):
    pass
