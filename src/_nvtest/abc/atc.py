import abc

from ..status import Status


class AbstractTestCase(abc.ABC):
    """Abstract test case"""

    def __init__(self) -> None:
        self._cpu_ids: list[int] = []
        self._gpu_ids: list[int] = []

    @property
    def cpu_ids(self) -> list[int]:
        return self._cpu_ids

    def assign_cpu_ids(self, arg: list[int]) -> None:
        assert len(arg) == self.cpus
        self._cpu_ids = list(arg)

    @property
    def gpu_ids(self) -> list[int]:
        return self._gpu_ids

    def assign_gpu_ids(self, arg: list[int]) -> None:
        assert len(arg) == self.gpus
        self._gpu_ids = list(arg)

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

    @abc.abstractmethod
    def refresh(self) -> None: ...

    @abc.abstractmethod
    def command(self, stage: str = "test") -> list[str]: ...
