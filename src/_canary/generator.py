# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import errno
import fnmatch
import hashlib
import importlib
import os
from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from typing import Sequence

try:
    from typing import Self  # type: ignore
except ImportError:
    from typing_extensions import Self

from schema import Schema
from schema import Type

from .ir import JobSpecIR
from .util import json_helper as json
from .util import reducer
from .util.logging import get_logger
from .util.reducer import unique

if TYPE_CHECKING:
    from .jobspec import JobSpec


WhenType = str | dict[str, str]
logger = get_logger(__name__)


def flatten_unique(xss: list[list[str]]) -> list[str]:
    return unique(reducer.concat(xss))


class AbstractSpecGenerator(ABC):
    """The AbstractTestGenerator is an abstract object representing a test file that
    can generate jobs

    Args:
      root: The base test directory, or file path if ``path`` is not given
      path: The file path, relative to root

    To create a test generator, simply subclass :class:`~AbstractTestGenerator` and register the
    containing file as an ``canary`` plugin.  The subclass will be added to the command registry
    and added to the set of available test generators.

    All ``canary`` builtin generators are implemented as plugins.

    Examples:

    .. code-block:: python

       from typing import Optional

       import canary

       class MyGenerator(canary.AbstractTestGenerator):
           file_patterns = ("*.suffix",)

           def describe(self, on_options: list[str] | None = None) -> str:
               ...

           def lock(self, on_options: list[str] | None = None) -> list[canary.JobSpecIR]:
               ...

    """

    file_patterns: ClassVar[tuple[str, ...]] = ()

    def __init__(self, root: str, path: str | None = None) -> None:
        if path is None:
            root, path = os.path.split(root)
        self.root = os.path.abspath(root)
        self.path = path
        self.file = Path(self.root).joinpath(self.path)
        if not self.file.exists():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.file)
        self.name = self.file.stem

        sha = hashlib.sha256()
        with open(self.file, "rb") as fh:
            data = fh.read()
            sha.update(data)
        self.sha256: str = sha.hexdigest()
        self.id: str = hashlib.sha256(self.file.as_posix().encode("utf-8")).hexdigest()[:20]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(file={self.file.as_posix()!r})"

    @classmethod
    def factory(cls, root: str, path: str | None = None) -> Self | None:
        f = root if path is None else path
        if cls.matches(f):
            return cls(root, path=path)
        return None

    @classmethod
    def matches(cls, path: str) -> str | None:
        """Is the file at ``path`` a test file?"""
        name = os.path.basename(path)
        for pattern in cls.file_patterns:
            if fnmatch.fnmatchcase(name, pattern):
                return pattern
        return None

    def describe(self, on_options: list[str] | None = None) -> str:
        """Return a description of the test"""
        return repr(self)

    @abstractmethod
    def lock(self, on_options: list[str] | None = None) -> Sequence["JobSpecIR | JobSpec"]:
        """Expand parameters and instantiate concrete test jobs

        Args:
          on_options: User specified options used to filter tests.  Jobs not matching
            ``on_options`` should be masked.

        Notes:

          For further discussion on filtering tests see :ref:`usage-filter`.

        """

    def asdict(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        state["root"] = self.root
        state["path"] = self.path
        state["mtime"] = self.file.stat().st_mtime
        return state

    @staticmethod
    def validate(data) -> Any:
        schema = Schema({"module": str, "classname": str, "params": {str: object}})
        return schema.validate(data)

    @staticmethod
    def reconstruct(serialized: str) -> "AbstractTestGenerator":
        meta = json.loads(serialized)
        AbstractTestGenerator.validate(meta)
        module = importlib.import_module(meta["module"])
        cls: Type[AbstractTestGenerator] = getattr(module, meta["classname"])
        params = meta["params"]
        generator = cls(params["root"], params["path"])
        return generator

    @staticmethod
    def create(root: str, path: str | None = None) -> "AbstractTestGenerator":
        from . import config

        if generator := config.pluginmanager.hook.canary_testcase_generator(root=root, path=path):
            return generator
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"{f} is not a test generator")

    def info(self) -> dict[str, Any]:
        return {}


AbstractTestGenerator = AbstractSpecGenerator
