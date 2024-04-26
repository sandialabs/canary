from types import ModuleType
from typing import Optional

from ..config.argparsing import Parser
from . import analyze
from . import autodoc
from . import commands
from . import config
from . import describe
from . import find
from . import info
from . import location
from . import log
from . import rebaseline
from . import report
from . import run
from . import status
from . import tree


def all_commands() -> list[ModuleType]:
    return [
        analyze,
        autodoc,
        commands,
        config,
        describe,
        find,
        info,
        location,
        log,
        report,
        rebaseline,
        run,
        status,
        tree,
    ]


def add_all_commands(parser: Parser, add_help_override: bool = False) -> None:
    for command in all_commands():
        parser.add_command(command, add_help_override=add_help_override)


def _cmd_name(command_module: ModuleType) -> str:
    return command_module.__name__.split(".")[-1]


def command_names() -> list[str]:
    return [_cmd_name(m) for m in all_commands()]


def get_command(command_name: str) -> Optional[ModuleType]:
    for command_module in all_commands():
        if _cmd_name(command_module) == command_name:
            return command_module
    return None
