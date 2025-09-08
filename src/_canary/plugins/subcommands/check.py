# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import importlib.resources as ir
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING
from typing import Any

from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Check()


stdout: Any = subprocess.PIPE
stderr: Any = subprocess.PIPE

logger = logging.get_logger(__name__)


class Action(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        action = getattr(namespace, "action", set())
        value = option_string[1:]
        action.add(value)
        namespace.action = action


class Check(CanarySubcommand):
    name = "check"
    description = "Run canary's internal checks"
    add_help = False

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument("-f", nargs=0, action=Action, help="run ruff format (default)")
        parser.add_argument("-c", nargs=0, action=Action, help="run ruff check (default)")
        parser.add_argument("-m", nargs=0, action=Action, help="run mypy (default)")
        parser.add_argument("-t", nargs=0, action=Action, help="run pytest")
        parser.add_argument("-C", nargs=0, action=Action, help="run coverage (default)")
        parser.add_argument("-e", nargs=0, action=Action, help="run examples test")
        parser.add_argument("-d", nargs=0, action=Action, help="make docs")
        parser.add_argument("-v", action="store_true", help="verbose")

    def execute(self, args: argparse.Namespace) -> int:
        global stdout
        global stderr
        if args.v:
            stdout = sys.stdout
            stderr = sys.stderr

        root = ir.files("canary").joinpath("../..")
        if not root.joinpath(".git").is_dir():
            raise ValueError("canary check must be run from a editable install of canary")
        self.root = os.path.normpath(str(root))
        if not hasattr(args, "action"):
            args.action = set("fcmC")
        if shutil.which("ruff") is None and "f" in args.action:
            raise ValueError("ruff must be on PATH to format and check code")
        if shutil.which("ruff") is None and "c" in args.action:
            raise ValueError("ruff must be on PATH to lint check code")
        if shutil.which("mypy") is None and "m" in args.action:
            raise ValueError("mypy must be on PATH to type check code")
        if "t" in args.action or "C" in args.action:
            if shutil.which("pytest") is None:
                raise ValueError("pytest must be on PATH to test code")
            if shutil.which("coverage") is None and "C" in args.action:
                raise ValueError("coverage must be on PATH to run coverage")

        if "f" in args.action:
            self.format_code(args)

        if "c" in args.action:
            self.lint_check_code(args)

        if "m" in args.action:
            self.type_check_code(args)

        if "t" in args.action or "C" in args.action:
            self.run_tests(args)

        if "d" in args.action:
            self.make_docs(args)

        logger.info("All checks complete!")

        return 0

    @staticmethod
    def find_pyt_files(top: str) -> list[str]:
        pyt_files: list[str] = []
        for dirname, _, files in os.walk(top):
            pyt_files.extend([os.path.join(dirname, f) for f in files if f.endswith(".pyt")])
        return pyt_files

    def format_code(self, args: argparse.Namespace):
        with working_dir(self.root):
            logger.info(f"Formatting examples in {self.root}/src/canary/examples")
            paths = Check.find_pyt_files("./src/canary/examples")
            ruff("format", *paths)
            ruff("format", "./src/canary/examples")

            logger.info(f"Formatting examples in {self.root}/docs/source/static")
            ruff("format", "./docs/source/static")

            logger.info(f"Formatting tests in {self.root}/tests")
            ruff("format", "./tests")

            logger.info(f"Formatting source in {self.root}/src")
            ruff("format", "./src")

    def lint_check_code(self, args: argparse.Namespace):
        with working_dir(self.root):
            logger.info(f"Lint checking examples in {self.root}/src/canary/examples")
            paths = Check.find_pyt_files("./src/canary/examples")
            ruff("check", "--fix", *paths)
            ruff("check", "--fix", "./src/canary/examples")

            logger.info(f"Lint checking examples in {self.root}/docs/source/static")
            ruff("check", "--fix", "./docs/source/static")

            logger.info(f"Lint checking tests in {self.root}/tests")
            ruff("check", "--fix", "./tests")

            logger.info(f"Lint checking source in {self.root}/src")
            ruff("check", "--fix", "./src")

    def type_check_code(self, args: argparse.Namespace):
        with working_dir(self.root):
            logger.info(f"Type checking source in {self.root}/src")
            mypy("./src")

    def run_tests(self, args: argparse.Namespace):
        if "e" in args.action:
            os.environ["CANARY_RUN_EXAMPLES_TEST"] = "1"
        with working_dir(self.root):
            if "C" not in args.action:
                logger.info(f"Running tests in {self.root}/tests")
                pytest("./tests")
            else:
                logger.info(f"Running coverage in {self.root}/tests")
                coverage("run")
                logger.info("Creating coverage report")
                coverage("report")
                coverage("html")

    def make_docs(self, args: argparse.Namespace):
        with working_dir(f"{self.root}/docs"):
            logger.info(f"Making documentation in {self.root}/docs")
            make("api-docs")
            make("clean")
            make("html")


def make(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"
    command = ["make", *args]
    cp = subprocess.run(command, **kwargs)
    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)
        if cp.stderr:
            sys.stderr.write(cp.stderr)
        raise ValueError(f"{' '.join(command)} failed!")
    return cp


def ruff(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"
    command = ["ruff", *args]
    cp = subprocess.run(command, **kwargs)
    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)
        if cp.stderr:
            sys.stderr.write(cp.stderr)
        raise ValueError(f"{' '.join(command)} failed!")
    return cp


def mypy(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"
    command = ["mypy", *args]
    cp = subprocess.run(command, **kwargs)
    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)
        if cp.stderr:
            sys.stderr.write(cp.stderr)
        raise ValueError(f"{' '.join(command)} failed!")
    return cp


def pytest(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"
    command = ["pytest", *args]
    cp = subprocess.run(command, **kwargs)
    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)
        if cp.stderr:
            sys.stderr.write(cp.stderr)
        raise ValueError(f"{' '.join(command)} failed!")
    return cp


def coverage(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    kwargs["encoding"] = "utf-8"
    command = ["coverage", *args]
    cp = subprocess.run(command, **kwargs)
    if cp.returncode != 0:
        if cp.stdout:
            sys.stdout.write(cp.stdout)
        if cp.stderr:
            sys.stderr.write(cp.stderr)
        raise ValueError(f"{' '.join(command)} failed!")
    return cp
