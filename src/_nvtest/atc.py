import abc
from typing import Generator

from .status import Status


class AbstractTestCase(abc.ABC):
    """Abstract test case"""

    def __init__(self) -> None:
        self._resources: list[tuple[str, str, int]] = []

    def __iter__(self) -> Generator["AbstractTestCase", None, None]:
        yield self

    def __len__(self) -> int:
        return 1

    def required_resources(self) -> list[list[tuple[str, int]]]:
        """Returns a list of resource"""
        group = [("cpus", 1) for i in range(self.cpus)]
        group.extend([("gpus", 1) for i in range(self.gpus)])
        return [group]

    def assign_resources(self, arg: list[tuple[str, str, int]]) -> None:
        self.resources = arg

    def release_resources(self) -> list[tuple[str, str, int]]:
        released = list(self.resources)
        self.resources.clear()
        return released

    @property
    def resources(self) -> list[tuple[str, str, int]]:
        return self._resources

    @resources.setter
    def resources(self, arg: list[tuple[str, str, int]]) -> None:
        self._resources.clear()
        self._resources.extend(arg)

    @property
    @abc.abstractmethod
    def id(self) -> str: ...

    @property
    @abc.abstractmethod
    def status(self) -> Status: ...

    @status.setter
    @abc.abstractmethod
    def status(self, arg: list[str]) -> None: ...

    @property
    @abc.abstractmethod
    def cpus(self) -> int: ...

    @property
    @abc.abstractmethod
    def gpus(self) -> int: ...

    @property
    @abc.abstractmethod
    def cputime(self) -> float: ...

    @property
    @abc.abstractmethod
    def runtime(self) -> float: ...

    @property
    @abc.abstractmethod
    def path(self) -> str: ...

    @abc.abstractmethod
    def refresh(self) -> None: ...

    @abc.abstractmethod
    def command(self, stage: str = "run") -> list[str]: ...

    @property
    def cpu_ids(self) -> list[str]:
        return [_[1] for _ in self.resources if _[0] == "cpus"]

    @property
    def exclusive(self) -> bool:
        return False

    @property
    def gpu_ids(self) -> list[str]:
        return [_[1] for _ in self.resources if _[0] == "gpus"]
