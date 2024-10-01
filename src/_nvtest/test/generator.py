import abc
import errno
import json
import os
from typing import IO
from typing import TYPE_CHECKING
from typing import Any
from typing import Optional
from typing import Type
from typing import Union

from ..resources import ResourceHandler
from ..test.case import TestCase

if TYPE_CHECKING:
    pass


class TestGenerator(abc.ABC):
    """The TestCaseGenerator is an abstract object representing a test file that
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

    REGISTRY: set[Type["TestGenerator"]] = set()

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
    @abc.abstractmethod
    def matches(cls, path: str) -> bool:
        pass

    @abc.abstractmethod
    def describe(
        self,
        keyword_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> str:
        pass

    @abc.abstractmethod
    def freeze(
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


def getstate(generator: TestGenerator) -> dict[str, str]:
    state: dict[str, str] = {}
    state["type"] = generator.__class__.__name__
    state["root"] = generator.root
    state["path"] = generator.path
    state["name"] = generator.name
    return state


def loadstate(state: dict[str, str]) -> TestGenerator:
    generator = factory(state["root"], state["path"])
    return generator


def load(fname: Union[str, IO[Any]]) -> TestGenerator:
    file: IO[Any]
    own_fh = False
    if isinstance(fname, str):
        file = open(fname, "r")
        own_fh = True
    else:
        file = fname
    state = json.load(file)
    generator = loadstate(state)
    if own_fh:
        file.close()
    return generator


def factory(root: str, path: Optional[str] = None) -> TestGenerator:
    for gen_type in TestGenerator.REGISTRY:
        if gen_type.matches(root if path is None else path):
            return gen_type(root, path=path)
    f = root if path is None else os.path.join(root, path)
    raise TypeError(f"No test generator for {f}")
