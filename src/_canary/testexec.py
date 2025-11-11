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
    stdout: str = "canary-out.txt"
    stderr: str | None = "canary-err.txt"
    dir: Path = dataclasses.field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.path = Path(self.path)
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

    def asdict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> "ExecutionSpace":
        return cls(
            root=Path(state["root"]),
            path=Path(state["path"]),
            stdout=state["stdout"],
            stderr=state["stderr"],
        )

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
        from .testinst import factory as test_instance_factory

        canary = importlib.import_module("canary")
        old_argv = sys.argv.copy()
        old_env = os.environ.copy()
        old_path = sys.path.copy()

        def get_instance():
            return test_instance_factory(case)

        def get_testcase():
            return case

        try:
            os.environ.update(case.environment)
            sys.path.insert(0, str(case.workspace.dir))

            canary.get_instance = get_instance
            canary.get_testcase = get_testcase
            canary.__testcase__ = case

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
            delattr(canary, "get_testcase")
            delattr(canary, "__testcase__")
            sys.argv.clear()
            sys.argv.extend(old_argv)
            os.environ.clear()
            os.environ.update(old_env)
            sys.path.clear()
            sys.path.extend(old_path)
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            case.save()

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
            os.environ.update(case.environment)
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
