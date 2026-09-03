# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary fetch`` subcommand for copying bundled assets into the working directory."""

import argparse
import importlib.resources as ir
import os
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..util.filesystem import force_copy
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Fetch())


class Fetch(CanarySubcommand):
    """Copy bundled Canary assets (examples directory or ``Canary.cmake``) into the current directory."""

    name = "fetch"
    description = "Fetch canary assets"

    def setup_parser(self, parser: "Parser") -> None:
        """Register the ``what`` positional with choices ``examples`` and ``canary.cmake``."""
        parser.add_argument(
            "what", choices=("examples", "canary.cmake"), type=str.lower, help="Asset to fetch"
        )

    def execute(self, args: argparse.Namespace) -> int:
        """Copy the requested asset into the current working directory and return 0."""
        if args.what == "examples":
            path = str(ir.files("canary").joinpath("docs/examples"))
            if os.path.exists("examples"):
                raise ValueError(f"A folder named 'examples' already exists at {os.getcwd()}")
            force_copy(path, os.path.basename(path))

        elif args.what.lower() == "canary.cmake":
            path = str(ir.files("canary_cmake").joinpath("Canary.cmake"))
            with open(os.path.basename(path), "w") as fh:
                fh.write(open(path).read())

        else:
            raise ValueError(f"Unknown option to fetch {args.what!r}")

        return 0
