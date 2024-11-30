import abc

from .status import Status


class AbstractTestCase(abc.ABC):
    """Abstract test case"""

    def __init__(self) -> None:
        self._cpu_ids: list[int] = []
        self._gpu_ids: list[int] = []

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
    def cpu_ids(self) -> list[int]:
        return self._cpu_ids

    @cpu_ids.setter
    def cpu_ids(self, arg: list[int]) -> None:
        if not self.exclusive and len(arg) < self.cpus:
            raise ValueError(f"{self}: received fewer cpu IDs than required!")
        self._cpu_ids = list(arg)

    @property
    def exclusive(self) -> bool:
        return False

    @property
    def gpu_ids(self) -> list[int]:
        return self._gpu_ids

    @gpu_ids.setter
    def gpu_ids(self, arg: list[int]) -> None:
        if not self.exclusive and len(arg) < self.gpus:
            raise ValueError(f"{self}: received fewer gpu IDs than required!")
        self._gpu_ids = list(arg)
