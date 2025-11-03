# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ...repo import Repo
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Info())


class Info(CanarySubcommand):
    name = "info"
    description = "Print information about test session"

    def execute(self, args: argparse.Namespace) -> int:
        repo = Repo()
        info = repo.info()
        print(f"Test sessions repository: {info['root']}")
        print(f"Version:       {info['version']}")
        print(f"Generators:    {info['generator_count']}")
        print(f"Sessions:      {info['session_count']}")
        print(f"Latest:        {info['latest_session']}")
        print(f"Tags:          {' '.join(info['tags'])}")
