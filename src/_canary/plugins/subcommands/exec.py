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
    parser.add_command(Exec())


class Exec(CanarySubcommand):
    name = "exec"
    description = "Execute test cases"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument(
            "tag",
            default=None,
            nargs="?",
            help="Execute test cases in selection tagged TAG [default: %(default)s]",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        repo = Repo.load()
        selection = repo.get_selection(tag=args.tag)
        with repo.session(selection) as session:
            session.run_all()
        return session.returncode
