from typing import Any

from .. import plugin
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
            case.result = Result("FAIL", reason=e.args[0])
        finally:
            for (_, func) in plugin.plugins("test", "teardown"):
                func(case)
        return vars(case)
