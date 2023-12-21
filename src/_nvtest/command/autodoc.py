import argparse
import os

import _nvtest.directives

from ..config.argparsing import make_argument_parser
from ..third_party import argparsewriter as aw
from ..util import tty
from ..util.filesystem import mkdirp

description = "Generate rst documentation files"


def setup_parser(subparser):
    subparser.add_argument("dest", help="Destination folder to write documentation")


def directives(args):
    # write rst to separate files
    names = [fun.__name__ for fun in _nvtest.directives.all_directives()]
    with open(os.path.join(args.dest, "index.rst"), "w") as fh:
        fh.write(".. _test-directives:\n\n")
        fh.write("Test Directives\n===============\n\n")
        fh.write(".. automodule:: _nvtest.directives.__init__\n\n")
        fh.write(".. toctree::\n   :maxdepth: 1\n\n")
        for name in names:
            fh.write(f"   {name}<{name}>\n")

    for name in names:
        with open(os.path.join(args.dest, f"{name}.rst"), "w") as fh:
            fh.write(f".. _directive-{name.replace('_', '-')}:\n\n")
            fh.write(f"{name}\n{'=' * len(name)}\n\n")
            fh.write(f".. autofunction:: _nvtest.directives.{name}.{name}\n")


def commands(args):
    # write rst to separate files
    tty.color.set_color_when("never")
    parser = make_argument_parser()
    _nvtest.command.add_commands(parser)
    if not os.path.isdir(args.dest):
        mkdirp(args.dest)
    writer = aw.ArgparseMultiRstWriter(parser.prog, args.dest)
    writer.write(parser)


def autodoc(args: argparse.Namespace) -> int:
    if not os.path.isdir(args.dest):
        mkdirp(args.dest)
    directives(os.path.join(args.dest, "directives"))
    commands(os.path.join(args.dest, "commands"))
    return 0
