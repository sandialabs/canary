from ..test.testcase import TestCase
from ..util.returncode import compute_returncode
from .argparsing import make_argument_parser
from .base import Session
from .run_tests import RunTests
from .config import Config
from .find import Find
from .info import Info
from .setup import Setup
from .describe import Describe
from .run_case import RunCase


class ExitCode:
    OK: int = 0
    INTERNAL_ERROR: int = 1
    INTERRUPTED: int = 3
    TIMEOUT: int = 5
    NO_TESTS_COLLECTED: int = 7

    @staticmethod
    def compute(cases: list[TestCase]) -> int:
        return compute_returncode(cases)


def factory(*, args: list[str], dir: str) -> Session:
    parser = make_argument_parser()
    for session_type in Session.registry:
        parser.add_command(session_type)
    opts = parser.parse_args(args)
    session_type = parser.get_command(opts.command)
    if session_type is None:
        raise ValueError(f"Unknown command {opts.command!r}")
    session = session_type(
        invocation_params=Session.InvocationParams(args=tuple(args), dir=dir)
    )
    return session
