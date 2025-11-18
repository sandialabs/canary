# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import importlib
import io
import os
import runpy
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import IO
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
    session: str | None = None
    dir: Path = dataclasses.field(default_factory=Path, init=False, repr=False)

    def __str__(self) -> str:
        return str(self.dir)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.path = Path(self.path)
        self.dir = self.root / self.path

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "ExecutionSpace":
        return cls(root=Path(state["root"]), path=Path(state["path"]), session=state["session"])

    def create(self, exist_ok: bool = False) -> None:
        self.dir.mkdir(parents=True, exist_ok=exist_ok)

    def remove(self, missing_ok: bool = False) -> None:
        if self.exists():
            shutil.rmtree(self.dir)
        elif not missing_ok:
            raise FileNotFoundError(self.dir)

    @contextmanager
    def enter(self) -> Generator[None, None, None]:
        current_cwd = Path.cwd()
        try:
            os.chdir(self.dir)
            yield
        finally:
            os.chdir(current_cwd)

    @contextmanager
    def openfile(self, name: Path | str, mode: str = "r") -> Generator[IO[Any], None, None]:
        try:
            fh = open(self.dir / name, mode=mode)
            yield fh
        finally:
            fh.close()

    def exists(self) -> bool:
        return self.dir.exists()

    def touch(self, name: Path | str, exist_ok: bool = False) -> None:
        (self.dir / name).touch(exist_ok=exist_ok)

    def unlink(self, name: Path | str, missing_ok: bool = False) -> None:
        (self.dir / name).unlink(missing_ok=missing_ok)

    def copy(self, src: Path, dst: Path | str | None) -> None:
        """Copy the file at ``src`` to this workspace with name ``dst``"""
        dst: Path = Path(dst or src.name)
        (self.dir / dst.name).unlink(missing_ok=True)
        (self.dir / dst.name).hardlink_to(src)

    def link(self, src: Path, dst: Path | str | None = None) -> None:
        """Symlink the file at ``src`` to this workspace with name ``dst``"""
        dst: Path = Path(dst or src.name)
        (self.dir / dst.name).unlink(missing_ok=True)
        (self.dir / dst.name).symlink_to(src)

    def joinpath(self, *parts: Path | str) -> Path:
        f = self.dir
        for part in parts:
            f /= part
        return f


class ExecutionPolicy(Protocol):
    def execute(self, case: "TestCase") -> int: ...


class PythonFileExecutionPolicy(ExecutionPolicy):
    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        """Temporarily patch:
        • canary.get_instance() to return `case`
        • canary.spec (optional)
        • sys.argv (optional)
        """
        from .testinst import factory as test_instance_factory

        canary = importlib.import_module("canary")
        old_argv = sys.argv.copy()
        old_env = os.environ.copy()
        old_cwd = Path.cwd()
        old_path = sys.path.copy()

        def get_instance():
            return test_instance_factory(case)

        def get_testcase():
            return case

        try:
            case.update_env(os.environ)
            sys.path.insert(0, str(case.workspace.dir))
            setattr(canary, "get_instance", get_instance)
            setattr(canary, "get_testcase", get_testcase)
            canary.__testcase__ = case
            sys.argv = [sys.executable, case.spec.file.name]
            if a := config.getoption("script_args"):
                sys.argv.extend(a)
            sys.stdout = open(case.stdout, "a")
            if case.stderr is None:
                sys.stderr = sys.stdout
            else:
                sys.stderr = open(case.stderr, "a")
            os.chdir(case.workspace.dir)

            yield

        finally:
            delattr(canary, "get_instance")
            delattr(canary, "get_testcase")
            delattr(canary, "__testcase__")
            os.chdir(old_cwd)
            sys.argv.clear()
            sys.argv.extend(old_argv)
            os.environ.clear()
            os.environ.update(old_env)
            sys.path.clear()
            sys.path.extend(old_path)
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__

    def execute(self, case: "TestCase") -> int:
        logger.debug(f"Starting {case.fullname} on pid {os.getpid()}")
        case.set_attribute(command=shlex.join(sys.argv))
        with self.context(case):
            runpy.run_path(case.spec.file.name, run_name="__main__")
        logger.debug(f"Finished {case.fullname}")
        return 0


class SubprocessExecutionPolicy(ExecutionPolicy):
    def __init__(self, args: list[str]) -> None:
        self.args = args

    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        old_env = os.environ.copy()
        old_cwd = Path.cwd()
        try:
            case.update_env(os.environ)
            os.chdir(case.workspace.dir)

            yield

        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)

    def execute(self, case: "TestCase") -> int:
        logger.debug(f"Starting {case.fullname} on pid {os.getpid()}")
        args: list[str] = list(self.args)
        with self.context(case):
            try:
                stdout = open(case.stdout, "a")
                if case.stderr is None:
                    stderr = subprocess.STDOUT
                else:
                    stderr = open(case.stderr, "a")
                if a := config.getoption("script_args"):
                    args.extend(a)
                case.set_attribute(command=shlex.join(args))
                cp = subprocess.run(args, stdout=stdout, stderr=stderr, check=False)
            finally:
                stdout.close()
                if isinstance(stderr, io.TextIOWrapper):
                    stderr.close()
        logger.debug(f"Finished {case.fullname}")
        return cp.returncode
