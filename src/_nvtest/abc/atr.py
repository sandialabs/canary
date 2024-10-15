import abc
from typing import Any
from typing import Optional
from typing import Type

from .. import config
from ..resource import ResourceHandler
from ..third_party.color import colorize
from ..util import logging
from .atc import AbstractTestCase


class AbstractTestRunner:
    scheduled = False
    REGISTRY: set[Type["AbstractTestRunner"]] = set()

    def __init_subclass__(cls) -> None:
        AbstractTestRunner.REGISTRY.add(cls)
        super().__init_subclass__()

    def __init__(self, rh: ResourceHandler) -> None:
        pass

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        prefix = colorize("@*b{==>} ")
        if not config.getoption("progress_bar"):
            logging.emit("%s%s\n" % (prefix, self.start_msg(case)))
        self.run(case)
        if not config.getoption("progress_bar"):
            logging.emit("%s%s\n" % (prefix, self.end_msg(case)))
        return None

    @staticmethod
    @abc.abstractmethod
    def matches(name: Optional[str]) -> bool: ...

    @abc.abstractmethod
    def start_msg(self, case: AbstractTestCase) -> str: ...

    @abc.abstractmethod
    def end_msg(self, case: AbstractTestCase) -> str: ...

    @staticmethod
    def factory(rh: ResourceHandler) -> "AbstractTestRunner":
        runner: "AbstractTestRunner"
        batch_runner = rh["batch:runner"]
        for T in AbstractTestRunner.REGISTRY:
            if T.matches(batch_runner):
                runner = T(rh)
                break
        else:
            raise ValueError(f"Cannot construct runner for batch:runner={batch_runner}")
        return runner

    @abc.abstractmethod
    def run(self, case: AbstractTestCase, stage: str = "test") -> None: ...
