# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...collect import Collector
from ...util import logging
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Add())


class Add(CanarySubcommand):
    name = "add"
    description = "Add test generators to Canary session"

    def setup_parser(self, parser: "Parser"):
        Collector.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        if args.specids:
            raise TypeError("Case specs incompatible with canary add")
        if args.runtag:
            raise TypeError("Tag name incompatible with canary add")
        if args.start:
            raise TypeError("Start directory incompatible with canary add")
        workspace.add(args.scanpaths, pedantic=True)
        return 0
