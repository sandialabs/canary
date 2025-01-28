from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING
from typing import Callable

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@dataclass
class CanarySubcommand:
    """Canary subcommand used when defining a Canary subcommand plugin hook.

    Args:
      name: Subcommand name (e.g., ``canary my-subcommand``)
      description: Subcommand description, shown in ``canary --help``
      execute: Called when the subcommand is invoked
      setup_parser: Called when the subcommand parser is initialized
      epilog: Epilog printed for ``canary my-subcommand --help``
      add_help: Whether to add subcommand to ``canary --help``

    """

    name: str
    description: str
    execute: Callable[[Namespace], int]
    setup_parser: Callable[["Parser"], None] | None = field(default=None)
    epilog: str | None = field(default=None)
    add_help: bool = field(default=True)


@dataclass
class CanaryReporterSubcommand:
    """Canary reporter class

    Args:
      name: Report type name (e.g., ``canary report my-report``)
      description: Subcommand description, shown in ``canary report --help``
      execute: Called when the subcommand is invoked
      setup_parser: Called when the subcommand parser is initialized

    """

    name: str
    description: str
    execute: Callable[[Namespace], None]
    setup_parser: Callable[["Parser"], None] | None = field(default=None)
