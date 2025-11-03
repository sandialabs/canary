# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

from ...repo import Repo
from ...util import logging
from ..hookspec import hookimpl
from ..types import CanarySubcommand

logger = logging.get_logger(__name__)

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Init())


class Init(CanarySubcommand):
    name = "init"
    description = "Initialize a Canary session"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument("-w", action="store_true", help="Wipe any existing session first")
        parser.add_argument(
            "path",
            default=os.getcwd(),
            nargs="?",
            help="Initialize session in this directory [default: %(default)s]",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        repo = Repo.create(Path(args.path).absolute(), force=args.w)
        logger.info(f"Initialized empty canary session created at {repo.root}")
        return 0
