# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
from typing import TYPE_CHECKING
from pathlib import Path

from ... import config
from ..builtin.reporting import determine_cases_to_show
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from ...util import logging
from ...repo import Repo

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
        parser.add_argument(
            "path",
            default=os.getcwd(),
            nargs="?",
            help="Initialize session in this directory [default: %(default)s]",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        repo = Repo.create(Path(args.path).absolute())
        logger.info(f"Canary session created at {repo.root.parent}")
        return 0
