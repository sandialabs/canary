# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Defines launchers for individual test cases"""

import importlib
import io
import os
import runpy
import shlex
import subprocess
import sys
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Generator
from typing import TextIO

from . import config
from .util import logging
from .util.module import load as load_module
from .util.shell import source_rcfile

if TYPE_CHECKING:
    from .testcase import TestCase

logger = logging.get_logger(__name__)


class Launcher(ABC):
    @abstractmethod
    def run(self, case: "TestCase") -> int: ...


class SubprocessLauncher(Launcher):
    def __init__(self, args: list[str]) -> None:
        self._default_args = args

    def default_args(self, case: "TestCase") -> list[str]:
        return list(self._default_args)

    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        old_env = os.environ.copy()
        old_cwd = Path.cwd()
        try:
            case.set_runtime_env(os.environ)
            for module in case.spec.modules or []:
                load_module(module)
            for rcfile in case.spec.rcfiles or []:
                source_rcfile(rcfile)
            os.chdir(case.workspace.dir)
            yield
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)

    def run(self, case: "TestCase") -> int:
        logger.debug(f"Starting {case.display_name()} on pid {os.getpid()}")
        with self.context(case):
            args = self.default_args(case)
            if a := config.getoption("script_args"):
                args.extend(a)
            if a := case.get_attribute("script_args"):
                args.extend(a)
            case.add_measurement("command_line", shlex.join(args))
            try:
                stdout = open(case.stdout, "a")
                stderr: TextIO | int
                if case.stderr is None:
                    stderr = subprocess.STDOUT
                else:
                    stderr = open(case.stderr, "a")
                cp = subprocess.run(args, stdout=stdout, stderr=stderr, check=False)
            finally:
                stdout.close()
                if isinstance(stderr, io.TextIOWrapper):
                    stderr.close()
        logger.debug(f"Finished {case.display_name()}")
        return cp.returncode


class PythonFileLauncher(SubprocessLauncher):
    def __init__(self):
        pass

    def default_args(self, case: "TestCase") -> list[str]:
        return [sys.executable, case.file.name]


class PythonRunpyLauncher(Launcher):
    @contextmanager
    def context(self, case: "TestCase") -> Generator[None, None, None]:
        """Temporarily patch:
        • canary.get_instance() to return `case`
        • canary.spec (optional)
        • sys.argv (optional)
        """
        from .testinst import from_testcase as test_instance_factory

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
            case.set_runtime_env(os.environ)
            for module in case.spec.modules or []:
                load_module(module)
            for rcfile in case.spec.rcfiles or []:
                source_rcfile(rcfile)
            sys.path.insert(0, str(case.workspace.dir))
            setattr(canary, "get_instance", get_instance)
            setattr(canary, "get_testcase", get_testcase)
            setattr(canary, "__testcase__", case)
            sys.argv = [sys.executable, case.spec.file.name]
            if a := config.getoption("script_args"):
                sys.argv.extend(a)
            if a := case.get_attribute("script_args"):
                sys.argv.extend(a)
            sys.stdout = open(case.stdout, "a")
            if case.stderr is None:
                sys.stderr = sys.stdout
            else:
                sys.stderr = open(case.stderr, "a")
            for module in case.spec.modules or []:
                load_module(module)
            for rcfile in case.spec.rcfiles or []:
                source_rcfile(rcfile)
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

    def run(self, case: "TestCase") -> int:
        logger.debug(f"Starting {case.display_name()} on pid {os.getpid()}")
        case.add_measurement("command_line", shlex.join(sys.argv))
        with self.context(case):
            runpy.run_path(case.spec.file.name, run_name="__main__")
        logger.debug(f"Finished {case.display_name()}")
        return 0
