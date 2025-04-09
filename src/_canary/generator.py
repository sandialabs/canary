# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import errno
import os
from abc import ABC
from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .test.case import TestCase


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

    def stop_recursion(self) -> bool:
        return False

    @classmethod
    @abstractmethod
    def matches(cls, path: str) -> bool:
        """Is the file at ``path`` a test file?"""

    @classmethod
    def always_matches(cls, path: str) -> bool:
        return cls.matches(path)

    @abstractmethod
    def describe(self, on_options: list[str] | None = None) -> str:
        """Return a description of the test"""

    @abstractmethod
    def lock(self, on_options: list[str] | None = None) -> list["TestCase"]:
        """Expand parameters and instantiate concrete test cases

        Args:
          on_options: User specified options used to filter tests.  Test cases not matching
            ``on_options`` should be masked.

        Notes:

          For further discussion on filtering tests see :ref:`usage-filter`.

        """

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
    def factory(root: str, path: str | None = None) -> "AbstractTestGenerator":
        from . import config

        for gen_type in config.plugin_manager.get_generators():
            if gen_type.always_matches(root if path is None else path):
                return gen_type(root, path=path)
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"No test generator for {f}")
