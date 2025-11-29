# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import errno
import hashlib
import os
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .testspec import UnresolvedSpec


class AbstractTestGenerator(ABC):
    """The AbstractTestCaseGenerator is an abstract object representing a test file that
    can generate test cases

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

           @classmethod
           def matches(cls, path: str) -> bool:
               ...

           def describe(self, on_options: list[str] | None = None) -> str:
               ...

           def lock(self, on_options: list[str] | None = None) -> list[canary.TestCase]:
               ...

    """

    def __init__(self, root: str, path: str | None = None) -> None:
        if path is None:
            root, path = os.path.split(root)
        self.root = os.path.abspath(root)
        self.path = path
        self.file = os.path.join(self.root, self.path)
        if not os.path.exists(self.file):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.file)
        self.name = os.path.splitext(os.path.basename(self.path))[0]
        sha = hashlib.sha256()
        with open(self.file, "rb") as fh:
            data = fh.read()
            sha.update(data)
        self.sha256: str = sha.hexdigest()
        self.id = hashlib.sha256(self.file.encode("utf-8")).hexdigest()[:20]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(file={self.file!r})"

    def stop_recursion(self) -> bool:
        return False

    @classmethod
    @abstractmethod
    def matches(cls, path: str) -> bool:
        """Is the file at ``path`` a test file?"""

    @classmethod
    def always_matches(cls, path: str) -> bool:
        return cls.matches(path)

    def describe(self, on_options: list[str] | None = None) -> str:
        """Return a description of the test"""
        return repr(self)

    @abstractmethod
    def lock(self, on_options: list[str] | None = None) -> list["UnresolvedSpec"]:
        """Expand parameters and instantiate concrete test cases

        Args:
          on_options: User specified options used to filter tests.  Test cases not matching
            ``on_options`` should be masked.

        Notes:

          For further discussion on filtering tests see :ref:`usage-filter`.

        """

    def asdict(self) -> dict[str, str]:
        state: dict[str, str] = {}
        state["root"] = self.root
        state["path"] = self.path
        state["sha256"] = self.sha256
        state["mtime"] = os.path.getmtime(self.file)
        return state

    @staticmethod
    def from_dict(state: dict[str, str]) -> "AbstractTestGenerator":
        return AbstractTestGenerator.factory(state["root"], state["path"])

    @staticmethod
    def factory(root: str, path: str | None = None) -> "AbstractTestGenerator":
        from . import config

        if generator := config.pluginmanager.hook.canary_testcase_generator(root=root, path=path):
            return generator
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"No test generator for {f}")
