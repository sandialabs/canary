import argparse
import os
import types

import nvtest.directives

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


def commands(dest):
    import _nvtest.command

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
