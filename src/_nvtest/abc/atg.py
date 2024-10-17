import errno
import os
from abc import ABC
from abc import abstractmethod
from typing import Generator
from typing import Optional
from typing import Type

from ..resource import ResourceHandler
from ..test.case import TestCase


class AbstractTestGenerator(ABC):
    """The AbstractTestCaseGenerator is an abstract object representing a test file that
    can generate test cases

    Parameters
    ----------
    root : str
        The base test directory, or file path if ``path`` is not given
    path : str
        The file path, relative to root

    Notes
    -----
    The ``TestCaseGenerator`` represents of an abstract test object.  The
    ``TestCaseGenerator`` facilitates the creation and management of ``TestCase``s
    based on a user-defined configuration.

    """

    REGISTRY: set[Type["AbstractTestGenerator"]] = set()

    def __init_subclass__(cls, **kwargs):
        cls.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    def __init__(self, root: str, path: Optional[str] = None) -> None:
        if path is None:
            root, path = os.path.split(root)
        self.root = os.path.abspath(root)
        self.path = path
        self.file = os.path.join(self.root, self.path)
        if not os.path.exists(self.file):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.file)
        self.name = os.path.splitext(os.path.basename(self.path))[0]

    @classmethod
    @abstractmethod
    def matches(cls, path: str) -> bool:
        pass

    @abstractmethod
    def describe(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> str:
        pass

    @abstractmethod
    def lock(
        self,
        cpus: Optional[list[int]] = None,
        gpus: Optional[list[int]] = None,
        nodes: Optional[list[int]] = None,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        parameter_expr: Optional[str] = None,
        timeout: Optional[float] = None,
        owners: Optional[set[str]] = None,
        env_mods: Optional[dict[str, str]] = None,
    ) -> list[TestCase]:
        pass

    def getstate(self) -> dict[str, str]:
        state: dict[str, str] = {}
        state["type"] = self.__class__.__name__
        state["root"] = self.root
        state["path"] = self.path
        state["name"] = self.name
        return state

    @staticmethod
    def from_state(state: dict[str, str]) -> "AbstractTestGenerator":
        generator = AbstractTestGenerator.factory(state["root"], state["path"])
        return generator

    @staticmethod
    def factory(root: str, path: Optional[str] = None) -> "AbstractTestGenerator":
        for gen_type in AbstractTestGenerator.REGISTRY:
            if gen_type.matches(root if path is None else path):
                return gen_type(root, path=path)
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"No test generator for {f}")


def generators() -> Generator[Type[AbstractTestGenerator], None, None]:
    for generator_class in AbstractTestGenerator.REGISTRY:
        yield generator_class
