import argparse
import os

import _nvtest.directives

from ..config.argparsing import make_argument_parser
from ..third_party import argparsewriter as aw
from ..util.color import set_color_when
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


def howto(dest):
    mkdirp(dest)
    with open(os.path.join(dest, "index.rst"), "w") as fh:
        fh.write(".. _howto-guides:\n\n")
        fh.write("How-to guides\n=============\n\n")
        fh.write(".. toctree::\n   :maxdepth: 1\n\n")
        root = os.path.dirname(_nvtest.__file__)
        tests = os.path.join(root, "../../tests")
        howto = os.path.join(tests, "howto")
        assert os.path.exists(os.path.join(howto, "__init__.py"))
        for file in sorted(os.listdir(howto)):
            if file.startswith("howto_") and file.endswith(".py"):
                module = os.path.splitext(os.path.basename(file))[0]
                name = module.split("_", 2)[-1]
                fh.write(f"   {name}\n")
                print(file, name)
                with open(os.path.join(dest, f"{name}.rst"), "w") as fp:
                    fp.write(f".. _howto-{name.replace('_', '-')}:\n\n")
                    fp.write(f".. automodule:: howto.{module}\n")


def autodoc(args: argparse.Namespace) -> int:
    set_color_when("never")
    if not os.path.isdir(args.dest):
        mkdirp(args.dest)
    directives(os.path.join(args.dest, "directives"))
    commands(os.path.join(args.dest, "commands"))
    howto(os.path.join(args.dest, "howto"))
    return 0
