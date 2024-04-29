import argparse
import os

import _nvtest.directives

from ..config.argparsing import make_argument_parser
from ..third_party import argparsewriter as aw
from ..third_party.color import set_color_when
from ..util.filesystem import mkdirp

description = "Generate rst documentation files"
add_help = False


def setup_parser(subparser):
    subparser.add_argument("dest", help="Destination folder to write documentation")


def directives(dest):
    mkdirp(dest)
    names = [fun.__name__ for fun in _nvtest.directives.all_directives()]
    with open(os.path.join(dest, "index.rst"), "w") as fh:
        fh.write(".. _test-directives:\n\n")
        fh.write("Test Directives\n===============\n\n")
        fh.write(".. automodule:: _nvtest.directives.__init__\n\n")
        fh.write(".. toctree::\n   :maxdepth: 1\n\n")
        for name in names:
            fh.write(f"   {name}<{name}>\n")

    for name in names:
        with open(os.path.join(dest, f"{name}.rst"), "w") as fh:
            fh.write(f".. _directive-{name.replace('_', '-')}:\n\n")
            fh.write(f"{name}\n{'=' * len(name)}\n\n")
            fh.write(f".. autofunction:: _nvtest.directives.{name}.{name}\n")


def commands(dest):
    mkdirp(dest)
    parser = make_argument_parser()
    _nvtest.command.add_all_commands(parser, add_help_override=True)
    writer = aw.ArgparseMultiRstWriter(parser.prog, dest)
    writer.write(parser)


def autodoc(args: argparse.Namespace) -> int:
    set_color_when("never")
    if not os.path.isdir(args.dest):
        mkdirp(args.dest)
    directives(os.path.join(args.dest, "directives"))
    commands(os.path.join(args.dest, "commands"))
    return 0
