import argparse
from abc import ABC
from abc import abstractmethod
from typing import Generator
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
    def add_help(self) -> bool:
        return True

    @property
    def epilog(self) -> Optional[str]:
        return None

    def setup_parser(self, parser: Parser) -> None: ...

    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int: ...

    @classmethod
    def cmd_name(cls) -> str:
        return cls.__name__.lower()


def commands() -> Generator[Type[Command], None, None]:
    for command_class in Command.REGISTRY:
        yield command_class
