# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from argparse import Namespace
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from ..config.argparsing import Parser


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


class CanaryReporter:
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
    default_output: str = "report.ext"

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="action", metavar="subcommands")
        p = subparsers.add_parser("create", help=f"Create {self.type.upper()} report")
        if self.multipage:
            p.add_argument(
                "--dest", default="$canary_work_tree", help="Write reports to this directory"
            )
        else:
            p.add_argument(
                "-o", dest="output", help=f"Output file name [default: {self.default_output}]"
            )

    def create(self, **kwargs: Any) -> None:
        raise NotImplementedError

    def not_implemented(self, **kwargs: Any) -> None:
        action = kwargs["action"]
        raise NotImplementedError(f"{self}: {action} method is not implemented")


class Result:
    def __init__(self, ok: bool | None = None, reason: str | None = None) -> None:
        if not ok:
            ok = not bool(reason)
        if not ok and not reason:
            raise ValueError(f"{self.__class__.__name__}(False) requires a reason")
        self.ok: bool = ok
        self.reason: str | None = reason

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        state = "ok" if self.ok else "fail"
        reason = f": {self.reason}" if self.reason else ""
        return f"<{self.__class__.__name__} {state}{reason}>"
