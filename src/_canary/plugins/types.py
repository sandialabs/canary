# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from argparse import Namespace
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..session import Session


class CanarySubcommand:
    """Canary subcommand used when defining a Canary subcommand plugin hook.

    Args:
      name: Subcommand name (e.g., ``canary my-subcommand``)
      description: Subcommand description, shown in ``canary --help``
      in_session: Subcommand should be exected inside a test session folder
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

    def in_session_note(self) -> str | None:
        note = f"Note: ``canary {self.name}`` must be executed within a test session folder. "
        note += "You can do this by either navigating to the folder or by specifying the path "
        note += f"with ``canary -C PATH {self.name} ...``"
        return note


class CanaryReport:
    """Canary reporter class

    Args:
      type: Report type name (e.g., ``canary report my-report``)
      description: Subcommand description, shown in ``canary report --help``
      execute: Called when the subcommand is invoked
      setup_parser: Called when the subcommand parser is initialized
      multipage: Whether the report is a multi-page report

    """

    type: str
    description: str
    multipage: bool = False

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="action", metavar="subcommands")
        p = subparsers.add_parser("create", help=f"Create {self.type.upper()} report")
        if self.multipage:
            p.add_argument(
                "--dest", default="$canary_work_tree", help="Write reports to this directory"
            )
        else:
            p.add_argument("-o", dest="output", help=f"Output file name [default: {self.type}.ext]")

    def create(self, session: "Session | None" = None, **kwargs: Any) -> None:
        raise NotImplementedError

    def not_implemented(self, session: "Session | None" = None, **kwargs: Any) -> None:
        action = kwargs["action"]
        raise NotImplementedError(f"{self}: {action} method is not implemented")
