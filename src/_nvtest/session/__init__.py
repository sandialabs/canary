from ..test.testcase import TestCase
from ..util.returncode import compute_returncode
from .base import Session


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
    session = Session(
        invocation_params=Session.InvocationParams(args=tuple(args), dir=dir)
    )
    return session
