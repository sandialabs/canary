import argparse
from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import Type

from .config.argparsing import Parser


class Command(ABC):
    REGISTRY: set[Type["Command"]] = set()

    def __init_subclass__(cls, **kwargs):
        Command.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def aliases(self) -> list[str]:
        return []

    @property
    def add_help(self) -> bool:
        return True

    @property
    def epilog(self) -> Optional[str]:
        return None

    @abstractmethod
    def setup_parser(self, parser: Parser) -> None: ...

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int: ...

    @classmethod
    def cmd_name(cls) -> str:
        return cls.__name__.lower()


def all_commands() -> list[Type]:
    return list(Command.REGISTRY)


def add_all_commands(parser: Parser, add_help_override: bool = False) -> None:
    for command_class in Command.REGISTRY:
        command = command_class()
        parser.add_command(command, add_help_override=add_help_override)


def command_names() -> list[str]:
    return [c.cmd_name() for c in Command.REGISTRY]


def get_command(command_name: str) -> Optional[Command]:
    for command_class in Command.REGISTRY:
        if command_class.cmd_name() == command_name:
            return command_class()
    return None
