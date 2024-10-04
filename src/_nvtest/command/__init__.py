from types import ModuleType
from typing import Optional
from typing import Type

from ..config.argparsing import Parser
from . import analyze
from . import config
from . import describe
from . import find
from . import help
from . import location
from . import log
from . import rebaseline
from . import report
from . import run
from . import self
from . import status
from . import tree
from .command import Command


def all_commands() -> list[Type]:
    return list(Command.REGISTRY)


def add_all_commands(parser: Parser, add_help_override: bool = False) -> None:
    for command_class in Command.REGISTRY:
        parser.add_command(command_class(), add_help_override=add_help_override)


def _cmd_name(command_class: Type) -> str:
    return command_class.__name__.lower()


def command_names() -> list[str]:
    return [c.__name__.lower() for c in Command.REGISTRY]


def get_command(command_name: str) -> Optional[Type]:
    for command_class in Command.REGISTRY:
        if _cmd_name(command_class) == command_name:
            return command_class
    return None
