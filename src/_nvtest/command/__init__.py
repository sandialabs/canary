from ..config.argparsing import Parser
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


def add_commands(parser: Parser) -> None:
    parser.add_command(config)
    parser.add_command(convert)
    parser.add_command(describe)
    parser.add_command(find)
    parser.add_command(python)
    parser.add_command(report)
    parser.add_command(rebaseline)
    parser.add_command(run)
    parser.add_command(show)
    parser.add_command(status)
