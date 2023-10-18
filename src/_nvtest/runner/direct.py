from typing import Any

from ..test.enums import Result
from ..test.testcase import TestCase
from .base import Runner


class DirectRunner(Runner):
    name = "direct"

    @staticmethod
    def validate(items):
        if not isinstance(items, list) and not isinstance(items[0], TestCase):
            s = f"{items.__class__.__name__}"
            raise ValueError(
                f"DirectRunner is only compatible with list[TestCase], not {s}"
            )

    def __call__(self, case: TestCase, *args: Any) -> dict:
        try:
            case.run(*args)
        except BaseException as e:
            if isinstance(e.args[0], int):
                case.result = Result.from_returncode(e.args[0])
            else:
                case.result = Result("FAIL", reason=e.args[0])
        return {case.fullname: vars(case)}
