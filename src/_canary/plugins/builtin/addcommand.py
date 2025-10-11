# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Generator

from ... import config
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl(wrapper=True)
def canary_addcommand(parser: "Parser") -> Generator[None, None, None]:
    yield
    if commands := config.pluginmanager.hook.canary_subcommand():
        # Backward compatible: prefer canary_addcommand
        for command in commands:
            parser.add_command(command)
