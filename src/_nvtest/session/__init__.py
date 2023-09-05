from ..config import Config
from ..test.testcase import TestCase
from ..util.returncode import compute_returncode
from .base import Session  # noqa: F401


class ExitCode:
    OK: int = 0
    INTERNAL_ERROR: int = 1
    INTERRUPTED: int = 3
    TIMEOUT: int = 5
    NO_TESTS_COLLECTED: int = 7

    @staticmethod
    def compute(cases: list[TestCase]) -> int:
        return compute_returncode(cases)


def factory(config: Config):
    opts = config.option
    session_type = config.parser.get_command(opts.command)
    if session_type is None:
        raise ValueError(f"Unknown command {opts.command!r}")
    return session_type(config)
