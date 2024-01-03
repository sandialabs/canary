from typing import TYPE_CHECKING
from typing import Any
from typing import Union

from ..test.partition import Partition
from ..test.testcase import TestCase

if TYPE_CHECKING:
    from ..session import Session


class Runner:
    name: str
    default_args: list[str] = []

    def __init__(self, session: "Session", *args: Any):
        self.options: list[Any] = list(args)
        self.work_tree = session.work_tree
        self.stage = session.stage

    @classmethod
    def validate(cls, *args):
        raise NotImplementedError

    def setup(self, *args, **kwargs):
        raise NotImplementedError

    def __call__(
        self, entity: Union[TestCase, Partition], kwds: dict[str, Any]
    ) -> dict[str, dict]:
        return self.run(entity, **kwds)

    def run(self, *args, **kwargs):
        raise NotImplementedError

    def add_default_args(self, *args):
        if self.default_args is None:
            self.default_args = []
        self.default_args.extend([str(_) for _ in args])
