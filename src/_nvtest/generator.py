import errno
import os
from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import Type

from .resource import ResourceHandler
from .test.case import TestCase


class AbstractTestGenerator(ABC):
    """The AbstractTestCaseGenerator is an abstract object representing a test file that
    can generate test cases

    Args:
      root: The base test directory, or file path if ``path`` is not given
      path: The file path, relative to root

    To create a test generator, simply subclass :class:`~AbstractTestGenerator` and register the
    containing file as an ``nvtest`` plugin.  The subclass will be added to the command registry
    and added to the set of available test generators.

    All ``nvtest`` builtin generators are implemented as plugins.

    Examples:

    .. code-block:: python

       from typing import Optional

       import nvtest
       from _nvtest.resource import ResourceHandler

       class MyGenerator(nvtest.AbstractTestGenerator):

           @classmethod
           def matches(cls, path: str) -> bool:
               ...

           def describe(
               self,
               keyword_expr: Optional[str] = None,
               parameter_expr: Optional[str] = None,
               on_options: Optional[list[str]] = None,
               rh: Optional[ResourceHandler] = None,
           ) -> str:
               ...

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
           ) -> list[nvtest.TestCase]:
               ...

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
        """Is the file at ``path`` a test file?"""

    @abstractmethod
    def describe(
        self,
        keyword_expr: Optional[str] = None,
        parameter_expr: Optional[str] = None,
        on_options: Optional[list[str]] = None,
        rh: Optional[ResourceHandler] = None,
    ) -> str:
        """Return a description of the test"""

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
        """Expand parameters and instantiate concrete test cases

        Args:
          cpus: [min_cpus, max_cpus] available to this test.  Tests requiring less/more cpus
            than the min/max, respectively, should be masked.
          gpus: [min_gpus, max_gpus] available to this test.  Tests requiring less/more gpus
            than the min/max, respectively, should be masked.
          nodes: [min_nodes, max_nodes] available to this test.  Tests requiring less/more nodes
            than the min/max, respectively, should be masked.
          keyword_expr: User specified keyword expression used to filter tests.  Test cases
            not matching ``keyword_expr`` should be masked.
          on_options: User specified options used to filter tests.  Test cases not matching
            ``on_options`` should be masked.
          parameter_expr: User specified parameter expression used to filter tests.  Test cases
            not matching ``parameter_expr`` should be masked.
          timeout: User specified global timeout.
          owners: Test cases not owned by one of ``owners`` should be masked.
          env_mods: Environment variables to add to each test case's environment.

        Notes:

          For further discussion on filtering tests see :ref:`basics-filter`.

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
    def factory(root: str, path: Optional[str] = None) -> "AbstractTestGenerator":
        for gen_type in AbstractTestGenerator.REGISTRY:
            if gen_type.matches(root if path is None else path):
                return gen_type(root, path=path)
        f = root if path is None else os.path.join(root, path)
        raise TypeError(f"No test generator for {f}")
