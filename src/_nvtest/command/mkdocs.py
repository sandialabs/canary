import argparse
import importlib.resources as ir
import subprocess

from ..util import logging
from ..util.filesystem import which
from ..util.filesystem import working_dir

description = "Make nvtest documents"
add_help = False


def setup_parser(subparser):
    subparser.add_argument("what", nargs="?", default="html")


def make(*args_in: str) -> int:
    args = [which("make", required=True)]
    args.extend(args_in)
    proc = subprocess.Popen(args)
    proc.wait()
    return proc.returncode


def mkdocs(args: argparse.Namespace) -> int:
    path = ir.files("_nvtest").joinpath("../../docs")
    if not path.is_dir():
        logging.warning("nvtest mkdocs must be run from a clone of nvtest")
        return 0
    with working_dir(str(path)):
        return make(args.what)
