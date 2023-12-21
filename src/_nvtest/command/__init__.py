from ..config.argparsing import Parser
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


def all_commands():
    return [
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
    ]


def add_commands(parser: Parser) -> None:
    for command in all_commands():
        parser.add_command(command)
