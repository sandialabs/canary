# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import types
from typing import TYPE_CHECKING

from ...third_party import argparsewriter as aw
from ...third_party.color import set_color_when
from ...util.filesystem import mkdirp
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Autodoc()


class Autodoc(CanarySubcommand):
    name = "autodoc"
    description = "Generate rst documentation files"
    add_help = False

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-d", dest="dest", default=".", help="Destination folder to write documentation"
        )

    def execute(self, args: argparse.Namespace) -> int:
        set_color_when("never")
        dest = os.path.abspath(args.dest)
        if not os.path.isdir(dest):
            mkdirp(dest)
        autodoc_directives(dest)
        autodoc_commands(dest)
        return 0


def autodoc_directives(dest: str) -> None:
    import canary.directives

    all_directives = []
    for name in dir(canary.directives):
        attr = getattr(canary.directives, name)
        if isinstance(attr, types.FunctionType) and attr.__doc__ and attr not in all_directives:
            all_directives.append(attr)
    names = sorted([fun.__name__ for fun in all_directives])
    with open(os.path.join(dest, "directives.rst"), "w") as fh:
        fh.write(".. _test-directives:\n\n")
        fh.write("Test Directives\n===============\n\n")
        fh.write(".. automodule:: canary.directives\n\n")
        fh.write(".. toctree::\n   :maxdepth: 1\n\n")
        for name in names:
            fh.write(f"   {name}<directives.{name}>\n")

    for name in names:
        with open(os.path.join(dest, f"directives.{name}.rst"), "w") as fh:
            fh.write(f".. _directive-{name.replace('_', '-')}:\n\n")
            fh.write(f"{name}\n{'=' * len(name)}\n\n")
            fh.write(f".. autofunction:: canary.directives.{name}\n")


def autodoc_commands(dest: str) -> None:
    from ... import config
    from ...config.argparsing import make_argument_parser

    parser = make_argument_parser()
    for command in config.plugin_manager.hook.canary_subcommand():
        parser.add_command(command)
    writer = aw.ArgparseMultiRstWriter(parser.prog, dest)
    writer.write(parser)
