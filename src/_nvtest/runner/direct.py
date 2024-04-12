from typing import Any

from ..test.status import Status
from ..test.testcase import TestCase
from .base import Runner


class DirectRunner(Runner):
    name = "direct"

    @staticmethod
    def validate(items):
        if not isinstance(items, list) and not isinstance(items[0], TestCase):
            s = f"{items.__class__.__name__}"
            raise ValueError(f"DirectRunner is only compatible with list[TestCase], not {s}")

    def setup(self, case: TestCase) -> None:
        ...

    def run(self, case: TestCase, **kwds: Any) -> dict[str, dict]:
        try:
            case.run()
        except BaseException as e:
            if isinstance(e.args[0], int):
                case.status = Status.from_returncode(e.args[0])
            else:
                case.status.set("failed", str(e))
                case.dump()
        return {case.fullname: vars(case)}
