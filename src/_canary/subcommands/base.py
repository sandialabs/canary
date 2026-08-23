# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from argparse import Namespace
from typing import TYPE_CHECKING

from ..util import logging

if TYPE_CHECKING:
    from ..config.argparsing import Parser


logger = logging.get_logger(__name__)


class CanarySubcommand:
    """Canary subcommand used when defining a Canary subcommand plugin hook.

    Args:
      name: Subcommand name (e.g., ``canary my-subcommand``)
      description: Subcommand description, shown in ``canary --help``
      in_repo: Subcommand should be exected inside a test session folder
      execute: Called when the subcommand is invoked
      setup_parser: Called when the subcommand parser is initialized
      epilog: Epilog printed for ``canary my-subcommand --help``
      add_help: Whether to add subcommand to ``canary --help``

    """

    name: str
    description: str
    epilog: str | None = None
    add_help: bool = True

    def setup_parser(self, parser: "Parser") -> None:
        pass

    def execute(self, args: Namespace) -> int:
        raise NotImplementedError
