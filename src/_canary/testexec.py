# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import datetime
import importlib
import multiprocessing
import os
import runpy
import shlex
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator
from typing import Protocol

from . import config
from .util import logging

if TYPE_CHECKING:
    from .testcase import TestCase

logger = logging.get_logger(__name__)

key_type = tuple[str, ...] | str
index_type = tuple[int, ...] | int


@dataclasses.dataclass
class ExecutionSpace:
    root: Path
    path: Path
    dir: Path = dataclasses.field(default=None, init=False, repr=False)
    stdout: str = "canary-out.txt"
    stderr: str | None = "canary-err.txt"

    def __post_init__(self) -> None:
        self.dir = self.root / self.path

    def create(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / self.stdout).unlink(missing_ok=True)
        if self.stderr is not None:
            (self.dir / self.stderr).unlink(missing_ok=True)
            (self.dir / self.stderr).touch()
        with open(self.dir / self.stdout, "w") as file:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
            file.write(f"[{stamp}] Creating workspace root at {self.dir}\n")

    @contextmanager
    def enter(self) -> Generator[None, None, None]:
        current_cwd = Path.cwd()
        try:
            os.chdir(self.dir)
            yield
        finally:
            os.chdir(current_cwd)

    def restore(self) -> None:
        (self.dir / self.stdout).unlink(missing_ok=True)
        with open(self.dir / self.stdout, "w") as file:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
            file.write(f"[{stamp}] Restoring workspace root\n")
        if self.stderr is not None:
            (self.dir / self.stderr).unlink(missing_ok=True)
            (self.dir / self.stderr).touch()

    def copy(self, src: Path, dst: Path | str | None) -> None:
        dst: Path = Path(dst or src.name)
        (self.dir / dst.name).unlink(missing_ok=True)
        with open(self.dir / self.stdout, "a") as file:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
            file.write(f"[{stamp}] Copying {src} to {Path(dst.name).absolute()}\n")
            (self.dir / dst.name).hardlink_to(src)

    def link(self, src: Path, dst: Path | str | None = None) -> None:
        dst: Path = Path(dst or src.name)
        (self.dir / dst.name).unlink(missing_ok=True)
        with open(self.dir / self.stdout, "a") as file:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S.%f")
            file.write(f"[{stamp}] Linking {src} to {Path(dst.name).absolute()}\n")
            (self.dir / dst.name).symlink_to(src)


class ExecutionPolicy(Protocol):
    def execute(self, case: "TestCase", queue: multiprocessing.Queue) -> int: ...


class PythonFilePolicy(ExecutionPolicy):
    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        """Temporarily patch:
        • canary.get_instance() to return `case`
        • canary.spec (optional)
        • sys.argv (optional)
        """
        canary = importlib.import_module("canary")
        old_argv = sys.argv.copy()
        old_env = os.environ.copy()
        old_path = sys.path.copy()

        def get_instance():
            return case

        try:
            os.environ.update(case.spec.environment)
            sys.path.insert(0, str(case.workspace.dir))

            canary.get_instance = get_instance
            canary.__instance__ = case
            case.parameters = Parameters(**case.spec.parameters)
            for dep in case.dependencies:
                dep.parameters = Parameters(**dep.spec.parameters)

            sys.argv = [sys.executable, case.spec.file.name]
            if a := config.getoption("script_args"):
                sys.argv.extend(a)

            sys.stdout = open(case.workspace.stdout, "a")
            if case.spec.stderr is None:
                sys.stderr = sys.stdout
            else:
                sys.stderr = open(case.workspace.stderr, "a")

            yield

        finally:
            delattr(canary, "get_instance")
            delattr(canary, "__instance__")
            sys.argv.clear()
            sys.argv.extend(old_argv)
            os.environ.clear()
            os.environ.update(old_env)
            sys.path.clear()
            sys.path.extend(old_path)
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__

    def execute(self, case: "TestCase", queue: multiprocessing.Queue) -> None:
        logger.debug(f"Starting {case.fullname} on pid {os.getpid()}")
        with self.context(case):
            runpy.run_path(case.spec.file, run_name="__main__")
        logger.debug(f"Finished {case.fullname}")
        return 0


class SubprocessPolicy(ExecutionPolicy):
    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        old_env = os.environ.copy()
        try:
            os.environ.update(case.spec.environment)
            pypath = case.workspace.dir
            if var := os.getenv("PYTHONPATH"):
                pypath = f"{pypath}:{var}"
            os.environ["PYTHONPATH"] = pypath

            yield

        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def execute(self, case: "TestCase", queue: multiprocessing.Queue) -> None:
        logger.debug(f"Starting {case.fullname} on pid {os.getpid()}")
        with self.context(case):
            try:
                stdout = open(case.spec.stdout, "a")
                if case.spec.stderr is None:
                    stderr = subprocess.STDOUT
                else:
                    stderr = open(case.spec.stderr, "a")
                args = shlex.split(case.spec.attributes("command"))
                cp = subprocess.run(args, stdout=stdout, stderr=stderr, check=False)
            finally:
                stdout.close()
                if hasattr(stderr, "write"):
                    stderr.close()
        logger.debug(f"Finished {case.fullname}")
        return cp.returncode


class Parameters:
    """Store parameters for a single test instance (case)

    Examples:

      >>> p = Parameters(a=1, b=2, c=3)
      >>> p['a']
      1
      >>> assert p.a == p['a']
      >>> p[('a', 'b')]
      (1, 2)
      >>> assert p['a,b'] == p[('a', 'b')]
      >>> p[('b', 'c', 'a')]
      (2, 3, 1)

    """

    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[str] = list(kwargs.keys())
        self._values: list[Any] = list(kwargs.values())

    def __str__(self) -> str:
        name = self.__class__.__name__
        s = ", ".join(f"{k}={v}" for k, v in self.items())
        return f"{name}({s})"

    def __contains__(self, arg: key_type) -> bool:
        return self.multi_index(arg) is not None

    def __getitem__(self, arg: key_type) -> Any:
        ix = self.multi_index(arg)
        if ix is None:
            raise KeyError(arg)
        elif isinstance(ix, int):
            return self._values[ix]
        return tuple([self._values[i] for i in ix])

    def __getattr__(self, key: str) -> Any:
        if key not in self._keys:
            raise AttributeError(f"Parameters object has no attribute {key!r}")
        index = self._keys.index(key)
        return self._values[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Parameters):
            return self._keys == other._keys and self._values == other._values
        assert isinstance(other, dict)
        if len(self._keys) != len(other):
            return False
        for key, value in other.items():
            if key not in self._keys:
                return False
            if self._keys[key] != value:
                return False
        return True

    def multi_index(self, arg: key_type) -> index_type | None:
        keys: tuple[str, ...]
        if isinstance(arg, str):
            if arg in self._keys:
                value = self._keys.index(arg)
                if isinstance(value, list):
                    return tuple(value)
                return value
            elif "," in arg:
                keys = tuple(arg.split(","))
            else:
                return None
        else:
            keys = tuple(arg)
        return tuple([self._keys.index(key) for key in keys])

    def items(self) -> Generator[Any, None, None]:
        for i, key in enumerate(self._keys):
            yield key, self._values[i]

    def keys(self) -> list[str]:
        return list(self._keys)

    def values(self) -> list[Any]:
        return list(self._values)

    def get(self, key: str, default: Any | None = None) -> Any | None:
        try:
            return self[key]
        except KeyError:
            return default

    def asdict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for i, key in enumerate(self._keys):
            d[key] = self._values[i]
        return d


class MultiParameters(Parameters):
    """Store parameters for a single test instance (case)

    Examples:

      >>> p = Parameters(a=[1, 2, 3], b=[4, 5, 6], c=[7, 8, 9])
      >>> a = p['a']
      >>> a
      (1, 2, 3)
      >>> b = p['b']
      >>> b
      (4, 5, 6)
      >>> for i, values in enumerate(p[('a', 'b')]):
      ...     assert values == (a[i], b[i])
      ...     print(values)
      (1, 4)
      (2, 5)

      As a consequence of the above, note the following:

      >>> x = p[('a',)]
      >>> x
      ((1,), (2,), (3,))

      etc.

    """

    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[str] = list(kwargs.keys())
        it = iter(kwargs.values())
        p_len = len(next(it))
        if not all(len(p) == p_len for p in it):
            raise ValueError(f"{self.__class__.__name__}: all arguments must be the same length")
        self._values: list[Any] = [tuple(_) for _ in kwargs.values()]

    def __getitem__(self, arg: key_type) -> Any:
        ix = self.multi_index(arg)
        if ix is None:
            raise KeyError(arg)
        elif isinstance(ix, int):
            return self._values[ix]
        rows = [self._values[i] for i in ix]
        # return colum data, now row data
        columns = tuple(zip(*rows))
        return columns
