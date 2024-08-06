import argparse
import glob
import importlib.resources as ir
import shlex
import subprocess
import sys

from ..util import logging
from ..util.filesystem import force_remove
from ..util.filesystem import which
from ..util.filesystem import working_dir

description = "Perform pre-commit testing, -fcmt implied if no other options are passed"
add_help = False


class Add(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        flags = getattr(args, self.dest, None) or set()
        flags.add(option_string.lstrip("-"))
        setattr(args, self.dest, flags)


def setup_parser(subparser):
    subparser.add_argument(
        "-f", nargs=0, dest="flags", action=Add, help="Run ruff format on source"
    )
    subparser.add_argument(
        "-c", nargs=0, dest="flags", action=Add, help="Run ruff check --fix on source"
    )
    subparser.add_argument("-m", nargs=0, dest="flags", action=Add, help="Run mypy on source")
    subparser.add_argument("-t", nargs=0, dest="flags", action=Add, help="Run unit tests")
    subparser.add_argument("-d", nargs=0, dest="flags", action=Add, help="Build documentation")
    subparser.add_argument("-v", action="store_true", dest="verbose_pc", help="Verbose")


def call(command: str, *args_in: str, verbose: bool = False) -> None:
    args = [which(command, required=True)]
    args.extend(args_in)
    print(shlex.join(args), end="\n" if verbose else " ... ", flush=True)
    tmpfile = ".tmp-pre-commit-subproc-out.txt"
    try:
        try:
            fh = sys.stdout if verbose else open(tmpfile, "w")
            proc = subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT)
            proc.wait()
        finally:
            if not verbose:
                fh.close()
        if proc.returncode != 0:
            print("failed", flush=True)
            if not verbose:
                print(open(tmpfile).read(), flush=True)
            raise SystemExit(f"Command failed: {shlex.join(args)}")
        else:
            print("success", flush=True)
    finally:
        force_remove(tmpfile)


def mypy(*args_in: str, verbose: bool = False) -> None:
    call("mypy", *args_in, verbose=verbose)


def ruff(*args_in: str, verbose: bool = False) -> None:
    call("ruff", *args_in, verbose=verbose)


def pytest(*args_in: str, verbose: bool = False) -> None:
    call("pytest", *args_in, verbose=verbose)


def make(*args_in: str, verbose: bool = False) -> None:
    call("make", *args_in, verbose=verbose)


def pre_commit(args: argparse.Namespace) -> int:
    flags = args.flags or {"f", "c", "m", "t"}
    root = ir.files("_nvtest").joinpath("../..")
    if not root.joinpath(".git").is_dir():
        logging.warning("nvtest pre-commit must be run from a clone of nvtest")
        return 0
    with working_dir(str(root)):
        if "f" in flags:
            ruff("format", "./src", verbose=args.verbose_pc)
            ruff("format", "./tests", verbose=args.verbose_pc)
        if "c" in flags:
            ruff("check", "--fix", "./src", verbose=args.verbose_pc)
            ruff("check", "--fix", "./tests", verbose=args.verbose_pc)
        if "m" in flags:
            mypy("./src", verbose=args.verbose_pc)
        if "t" in flags:
            force_remove("./TestResults")
            for dirname in glob.glob("./examples/TestResults*"):
                force_remove(dirname)
            pytest("./tests", verbose=args.verbose_pc)
            force_remove("./TestResults")
            for dirname in glob.glob("./examples/TestResults*"):
                force_remove(dirname)
    if "d" in flags:
        with working_dir(str(root.joinpath("docs"))):
            make("clean", verbose=args.verbose_pc)
            make("html", verbose=args.verbose_pc)
    return 0
