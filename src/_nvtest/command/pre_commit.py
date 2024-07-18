import argparse
import importlib.resources as ir
import subprocess

from ..util import logging
from ..util.filesystem import which
from ..util.filesystem import working_dir

description = "Peform pre-commit testing"
add_help = False


def setup_parser(subparser):
    subparser.add_argument("--docs", action="store_true", default=False)


def mypy(*args_in: str) -> None:
    args = [which("mypy", required=True)]
    args.extend(args_in)
    proc = subprocess.Popen(args)
    proc.wait()
    assert proc.returncode == 0


def ruff(*args_in: str) -> None:
    args = [which("ruff", required=True)]
    args.extend(args_in)
    proc = subprocess.Popen(args)
    proc.wait()
    assert proc.returncode == 0


def pytest(*args_in: str) -> None:
    args = [which("pytest", required=True)]
    args.extend(args_in)
    proc = subprocess.Popen(args)
    proc.wait()
    assert proc.returncode == 0


def pre_commit(args: argparse.Namespace) -> int:
    root = ir.files("_nvtest").joinpath("../..")
    if not root.joinpath(".git").is_dir():
        logging.warning("nvtest pre-commit must be run from a clone of nvtest")
        return 0
    with working_dir(str(root)):
        ruff("check", "--fix", "./src")
        ruff("format", "./src")
        ruff("check", "--fix", "./tests")
        ruff("format", "./tests")
        mypy("./src")
        pytest("./tests")
    if args.docs:
        with working_dir(str(root.joinpath("docs"))):
            proc = subprocess.Popen(["make", "clean"])
            proc.wait()
            proc = subprocess.Popen(["make", "html"])
            proc.wait()
    return 0
