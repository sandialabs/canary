import argparse
from abc import ABC
from abc import abstractmethod
from typing import Generator
from typing import Type

from _canary.config.argparsing import Parser


class Command(ABC):
    """Base class for all ``canary`` subcommands.

    To create a subcommand, simply subclass this class and register the containing file as a
    ``canary`` plugin.  The subclass will be added to the command registry and added to the set of
    available commands.

    All ``canary`` builtin subcommands are implemented as plugins.

    Examples:

    .. code-block:: python

       import argparse
       import canary

       class MyCommand(canary.Command):

           def description(self) -> str:
               return "A totally cool description"

           def setup_parser(self, parser: canary.Parser) -> None:
               parser.add_argument("-a", action="store_true", help="Flip an 'a'")

           def execute(self, args: argparse.Namespace) -> int:
                # Run the command

    """

    REGISTRY: set[Type["Command"]] = set()

    def __init_subclass__(cls, **kwargs):
        Command.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    @property
    @abstractmethod
    def description(self) -> str:
        """String describing what this function does.  This string appears in the ``canary -h``
        page"""

    @property
    def add_help(self) -> bool:
        return True

    @property
    def epilog(self) -> str | None:
        return None

    def setup_parser(self, parser: Parser) -> None:
        """Add arguments to parser for *this* subcommand"""

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int:
        """Run the subcommand and return an integer return code"""

    @classmethod
    def cmd_name(cls) -> str:
        return cls.__name__.lower()


def commands() -> Generator[Type[Command], None, None]:
    """Generator of all registered commands"""
    for command_class in Command.REGISTRY:
        yield command_class
