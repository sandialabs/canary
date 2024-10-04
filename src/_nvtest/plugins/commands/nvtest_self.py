import argparse
import glob
import importlib.resources as ir
import os
import re
import shlex
import subprocess
import sys
import types

import nvtest.directives

from _nvtest.config.argparsing import Parser
from _nvtest.config.argparsing import make_argument_parser
from _nvtest.third_party import argparsewriter as aw
from _nvtest.third_party.color import set_color_when
from _nvtest.util import logging
from _nvtest.util.filesystem import force_remove
from _nvtest.util.filesystem import mkdirp
from _nvtest.util.filesystem import which
from _nvtest.util.filesystem import working_dir
from _nvtest.command import Command


class Self(Command):
    @property
    def description(self) -> str:
        return "perform operations on this instance of nvtest"

    @property
    def add_help(self) -> bool:
        return False

    def setup_parser(self, parser: Parser):
        subparsers = parser.add_subparsers(dest="self_subparser", metavar="")

        subparser = subparsers.add_parser(
            "check",
            help="Perform pre-commit testing",
            epilog="-fcmt implied if no other options are passed",
        )
        subparser.add_argument(
            "-f", nargs=0, dest="flags", action=Add, help="Run ruff format on source"
        )
        subparser.add_argument(
            "-c", nargs=0, dest="flags", action=Add, help="Run ruff check --fix on source"
        )
        subparser.add_argument("-m", nargs=0, dest="flags", action=Add, help="Run mypy on source")
        subparser.add_argument("-t", nargs=0, dest="flags", action=Add, help="Run unit tests")
        subparser.add_argument("-d", nargs=0, dest="flags", action=Add, help="Build documentation")
        subparser.add_argument("-a", nargs=0, dest="flags", action=Add, help="Same as -mtdfc")
        subparser.add_argument("-v", action="store_true", dest="verbose_pc", help="Verbose")

        subparser = subparsers.add_parser(
            "update", help="Update this installation in place with the most current"
        )
        subparser.add_argument(
            "-b",
            metavar="branch",
            default="main",
            help="Use this branch (or committish) to fetch latest version [default: %(default)s]",
        )
        subparser.add_argument(
            "--pip-args",
            metavar="args",
            dest="default_pip_args",
            help="Pass these arguments directly to pip",
        )
        subparser.add_argument(
            "--pip-install-args",
            metavar="args",
            dest="default_pip_install_args",
            help="Pass these arguments directly to pip install",
        )

        subparser = subparsers.add_parser("mkdocs", help="Make nvtest documents")
        subparser.add_argument("what", nargs="?", default="html")
        subparser.add_argument(
            "-c", action="store_true", dest="clean_first", help="Run make clean first"
        )

        subparser = subparsers.add_parser("autodoc", help="Generate rst documentation files")
        subparser.add_argument("dest", help="Destination folder to write documentation")

    def execute(self, args: argparse.Namespace) -> int:
        if args.self_subparser == "check":
            return pre_commit(args)
        elif args.self_subparser == "update":
            return update(args)
        elif args.self_subparser == "mkdocs":
            return mkdocs(args)
        elif args.self_subparser == "autodoc":
            return autodoc(args)
        raise ValueError(f"nvtest self: unknown subcommand: {args.self_subparser}")


def call(command: str, *args_in: str, verbose: bool = False) -> None:
    file = which(command)
    if file is None:
        raise ValueError(f"{command}: command not found")
    args = [file]
    args.extend(args_in)
    print(shlex.join(args), end="\n" if verbose else " ... ", flush=True)
    tmpfile = ".tmp-nvtest-self-op-subproc-out.txt"
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


class Add(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        flags = getattr(args, self.dest, None) or set()
        flags.add(option_string.lstrip("-"))
        setattr(args, self.dest, flags)


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
    if "a" in flags:
        flags.remove("a")
        flags.update("fcmtd")
    root = ir.files("_nvtest").joinpath("../..")
    if not root.joinpath(".git").is_dir():
        logging.warning("nvtest pre-commit must be run from a clone of nvtest")
        return 0
    with working_dir(str(root)):
        print(f"cd {os.getcwd()}")
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
        args.what = "html"
        args.clean_first = True
        mkdocs(args)
    return 0


def mkdocs(args: argparse.Namespace) -> int:
    root = ir.files("_nvtest").joinpath("../..")
    if not root.joinpath(".git").is_dir():
        logging.warning("nvtest mkdocs must be run from a clone of nvtest")
        return 0
    with working_dir(str(root.joinpath("docs"))):
        print(f"cd {os.getcwd()}")
        if args.clean_first:
            make("clean", verbose=args.verbose_pc)
        make(args.what, verbose=args.verbose_pc)
    return 0


def is_sandia_system() -> bool:
    if "SNLSYSTEM" in os.environ:
        return True
    if "SNLCLUSTER" in os.environ:
        return True
    if "SNLSITE" in os.environ:
        return True
    if re.search("s[0-9]{7}", os.uname().nodename):
        return True
    return False


def snl_pip_proxy_args() -> list[str]:
    return [
        "--trusted-host=pypi.org",
        "--trusted-host=pypi.python.org",
        "--trusted-host=files.pythonhosted.org",
    ]


def set_snl_pip_env():
    os.environ["PIP_INDEX"] = "https://nexus.web.sandia.gov/repository/pypi-proxy/pypi"
    os.environ["PIP_INDEX_URL"] = "https://nexus.web.sandia.gov/repository/pypi-proxy/simple"
    os.environ["PIP_TRUSTED_HOST"] = "nexus.web.sandia.gov"


def update(args: argparse.Namespace) -> int:
    iargs: list[str] = [] if not args.default_pip_args else shlex.split(args.default_pip_args)
    iargs.extend(["install", "--upgrade"])
    if args.default_pip_install_args:
        iargs.extend(shlex.split(args.default_pip_install_args))
    if is_sandia_system():
        iargs.extend(snl_pip_proxy_args())
        set_snl_pip_env()
    url = "git+ssh://git@cee-gitlab.sandia.gov/alegra/tools/nvtest"
    if args.branch:
        url += f"@{args.branch}"
    if "-e" in iargs or "--editable" in iargs:
        try:
            iargs.append(iargs.pop(iargs.index("-e")))
        except ValueError:
            iargs.append(iargs.pop(iargs.index("--editable")))
        url += "#egg=nvtest"
    iargs.append(url)
    call(sys.executable, "-m", "pip", *iargs, verbose=args.verbose)
    return 0


def autodoc_directives(dest):
    mkdirp(dest)
    all_directives = []
    for name in dir(nvtest.directives):
        attr = getattr(nvtest.directives, name)
        if isinstance(attr, types.FunctionType) and attr.__doc__ and attr not in all_directives:
            all_directives.append(attr)
    names = [fun.__name__ for fun in all_directives]
    with open(os.path.join(dest, "index.rst"), "w") as fh:
        fh.write(".. _test-directives:\n\n")
        fh.write("Test Directives\n===============\n\n")
        fh.write(".. automodule:: nvtest.directives\n\n")
        fh.write(".. toctree::\n   :maxdepth: 1\n\n")
        for name in names:
            fh.write(f"   {name}<{name}>\n")

    for name in names:
        with open(os.path.join(dest, f"{name}.rst"), "w") as fh:
            fh.write(f".. _directive-{name.replace('_', '-')}:\n\n")
            fh.write(f"{name}\n{'=' * len(name)}\n\n")
            fh.write(f".. autofunction:: nvtest.directives.{name}\n")


def autodoc_commands(dest):
    import _nvtest.command

    mkdirp(dest)
    parser = make_argument_parser()
    _nvtest.command.add_all_commands(parser)
    writer = aw.ArgparseMultiRstWriter(parser.prog, dest)
    writer.write(parser)


def autodoc(args: argparse.Namespace) -> int:
    set_color_when("never")
    if not os.path.isdir(args.dest):
        mkdirp(args.dest)
    autodoc_directives(os.path.join(args.dest, "directives"))
    autodoc_commands(os.path.join(args.dest, "commands"))
    return 0
