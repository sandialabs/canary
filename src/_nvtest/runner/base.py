from types import SimpleNamespace
from typing import Any


class Runner:
    name: str
    default_args: list[str] = []

    def __init__(self, machine_config: SimpleNamespace, *args: Any):
        self.machine_config = machine_config
        self.options: list[Any] = list(args)

    @classmethod
    def validate(cls, *args):
        raise NotImplementedError

    def __call__(self, *args, **kwargs):
        raise NotImplementedError

    def add_default_args(self, *args):
        if self.default_args is None:
            self.default_args = []
        self.default_args.extend([str(_) for _ in args])
