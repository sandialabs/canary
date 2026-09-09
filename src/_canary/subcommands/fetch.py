# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Implements the ``canary fetch`` subcommand for copying bundled assets into the working directory.

Built-in fetchable assets are registered by plugins via the
``canary_fetch_subcommand`` / ``canary_fetch_execute`` hook pair, which mirrors
the ``canary_query_subcommand`` / ``canary_query_execute`` pattern used by
``canary query``.

Built-in assets
---------------
examples     — copy the bundled examples directory (registered by ``canary``)
canary.cmake — copy ``Canary.cmake`` (registered by ``canary_cmake``)

Plugin authors
--------------
To make a new asset fetchable::

    @canary.hookimpl
    def canary_fetch_subcommand(subparsers):
        subparsers.add_parser("myasset", help="Fetch MyAsset")

    @canary.hookimpl
    def canary_fetch_execute(args):
        if args.fetch_what == "myasset":
            # copy the asset …
            return 0
        return None   # not handled — pass to next plugin
"""

import argparse
from typing import TYPE_CHECKING

import canary

from ..hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Fetch())


class Fetch(CanarySubcommand):
    """Copy a bundled Canary asset into the current directory."""

    name = "fetch"
    description = (
        "Fetch a Canary asset into the current directory.\n\n"
        "Available assets are contributed by installed plugins.\n\n"
        "Examples:\n"
        "  canary fetch examples\n"
        "  canary fetch canary.cmake\n"
    )

    def setup_parser(self, parser: "Parser") -> None:
        """Register built-in and plugin-provided asset subparsers."""
        sub = parser.add_subparsers(dest="fetch_what", metavar="ASSET")
        # Let plugins (including the canary and canary_cmake builtins) register
        # their own sub-parsers.  The hook is additive (not firstresult) so
        # every installed plugin gets a chance to add its entries.
        canary.config.pluginmanager.hook.canary_fetch_subcommand(subparsers=sub)

    def execute(self, args: argparse.Namespace) -> int:
        """Dispatch to the first plugin that handles ``args.fetch_what``."""
        if not getattr(args, "fetch_what", None):
            print(self.description)
            return 1
        result = canary.config.pluginmanager.hook.canary_fetch_execute(args=args)
        if result is not None:
            return result
        print(self.description)
        return 1
