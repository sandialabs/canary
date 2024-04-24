import abc

from ..util import logging
from .status import Status


class Runner(abc.ABC):
    def __call__(self, *args: str, verbose: bool = True) -> None:
        if verbose:
            logging.emit(self.start_msg() + "\n")
        self.run(*args)
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
    def devices(self) -> int: ...

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
    def run(self, *args: str) -> None: ...

    @abc.abstractmethod
    def refresh(self) -> None: ...
