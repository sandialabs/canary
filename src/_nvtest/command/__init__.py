from types import ModuleType
from typing import Optional

from ..config.argparsing import Parser
from . import analyze
from . import autodoc
from . import commands
from . import config
from . import convert
from . import describe
from . import find
from . import python
from . import rebaseline
from . import report
from . import run
from . import show
from . import status
from . import tree


def all_commands() -> list[ModuleType]:
    return [
        analyze,
        autodoc,
        commands,
        config,
        convert,
        describe,
        find,
        python,
        report,
        rebaseline,
        run,
        show,
        status,
        tree,
    ]


def add_all_commands(parser: Parser) -> None:
    for command in all_commands():
        parser.add_command(command)


def _cmd_name(command_module: ModuleType) -> str:
    return command_module.__name__.split(".")[-1]


def get_command(command_name: str) -> Optional[ModuleType]:
    for command_module in all_commands():
        if _cmd_name(command_module) == command_name:
            return command_module
    return None
