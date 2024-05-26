import abc
from typing import Any

from ..util import logging
from .status import Status


class Runner(abc.ABC):
    def __call__(self, *args: str, **kwargs: Any) -> None:
        verbose = kwargs.get("verbose", False)
        if verbose:
            logging.emit(self.start_msg() + "\n")
        self.run(*args, **kwargs)
        if verbose:
            logging.emit(self.end_msg() + "\n")
        return None

    @property
    @abc.abstractmethod
    def status(self) -> Status: ...

    @status.setter
    @abc.abstractmethod
    def status(self, arg: list[str]) -> None: ...

    @property
    @abc.abstractmethod
    def processors(self) -> int: ...

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
    def start_msg(self) -> str: ...

    @abc.abstractmethod
    def end_msg(self) -> str: ...

    @abc.abstractmethod
    def run(self, *args: str, timeoutx: float = 1.0) -> None: ...

    @abc.abstractmethod
    def refresh(self) -> None: ...
