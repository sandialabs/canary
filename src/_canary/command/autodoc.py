import argparse
import os
import types

from _canary.config.argparsing import Parser
from _canary.config.argparsing import make_argument_parser
from _canary.third_party import argparsewriter as aw
from _canary.third_party.color import set_color_when
from _canary.util.filesystem import mkdirp

from .base import Command


class Autodoc(Command):
    @property
    def description(self) -> str:
        return "Generate rst documentation files"

    @property
    def add_help(self) -> bool:
        return False

    def setup_parser(self, parser: Parser):
        parser.add_argument(
            "-d", dest="dest", default=".", help="Destination folder to write documentation"
        )

    def execute(self, args: argparse.Namespace) -> int:
        set_color_when("never")
        self.dest = os.path.abspath(args.dest)
        if not os.path.isdir(self.dest):
            mkdirp(self.dest)
        self.autodoc_directives()
        self.autodoc_commands()
        return 0

    def autodoc_directives(self) -> None:
        import canary.directives

        all_directives = []
        for name in dir(canary.directives):
            attr = getattr(canary.directives, name)
            if isinstance(attr, types.FunctionType) and attr.__doc__ and attr not in all_directives:
                all_directives.append(attr)
        names = sorted([fun.__name__ for fun in all_directives])
        with open(os.path.join(self.dest, "directives.rst"), "w") as fh:
            fh.write(".. _test-directives:\n\n")
            fh.write("Test Directives\n===============\n\n")
            fh.write(".. automodule:: canary.directives\n\n")
            fh.write(".. toctree::\n   :maxdepth: 1\n\n")
            for name in names:
                fh.write(f"   {name}<directives.{name}>\n")

        for name in names:
            with open(os.path.join(self.dest, f"directives.{name}.rst"), "w") as fh:
                fh.write(f".. _directive-{name.replace('_', '-')}:\n\n")
                fh.write(f"{name}\n{'=' * len(name)}\n\n")
                fh.write(f".. autofunction:: canary.directives.{name}\n")

    def autodoc_commands(self) -> None:
        parser = make_argument_parser()
        parser.add_all_commands()
        writer = aw.ArgparseMultiRstWriter(parser.prog, self.dest)
        writer.write(parser)
