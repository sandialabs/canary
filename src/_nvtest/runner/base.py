from typing import TYPE_CHECKING
from typing import Any

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

    def __call__(self, *args, **kwargs):
        raise NotImplementedError

    def add_default_args(self, *args):
        if self.default_args is None:
            self.default_args = []
        self.default_args.extend([str(_) for _ in args])
