# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Generator

from ...hookspec import hookimpl
from ...third_party.monkeypatch import monkeypatch

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl(wrapper=True)
def canary_addoption(parser: "Parser") -> Generator[None, None, None]:
    with monkeypatch.context() as mp:
        mp.setattr(parser, "add_argument", parser.add_plugin_argument)
        mp.setattr(parser, "add_argument_group", parser.add_plugin_argument_group)
        yield
