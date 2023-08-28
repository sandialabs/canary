from types import SimpleNamespace
from typing import Any
from typing import Optional
from typing import Type

from ..util import tty
from .base import Runner
from .direct import DirectRunner
from .shell import ShellRunner
from .slurm import SlurmRunner

valid_runners = ("shell", "direct", "slurm")


def factory(
    name: str,
    work_items: list[Any],
    *,
    machine_config: SimpleNamespace,
    options: Optional[list[Any]] = None,
) -> Runner:
    runner: Type[Runner]
    tty.verbose("Setting up the test runner")
    for runner in (ShellRunner, SlurmRunner, DirectRunner):
        if runner.name == name:
            break
    else:
        valid = ", ".join(valid_runners)
        raise ValueError(f"Unknown runner {name!r}, choose from {valid}")
    runner.validate(work_items)
    opts: list[Any] = options or []
    tty.verbose(f"Runner type = {runner.__class__.__name__}")
    return runner(machine_config, *opts)
