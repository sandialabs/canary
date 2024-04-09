from typing import TYPE_CHECKING
from typing import Any
from typing import Type
from typing import Union

from ..util import tty
from .base import Runner
from .direct import DirectRunner
from .shell import ShellRunner
from .slurm import SlurmRunner

if TYPE_CHECKING:
    from _nvtest.session import Session

valid_schedulers = (ShellRunner.name, SlurmRunner.name)


def factory(
    name: Union[None, str],
    session: "Session",
    **kwargs: Any,
) -> Runner:
    runner: Type[Runner]
    tty.debug("Setting up the test runner")
    if name is None or name == "direct":
        runner = DirectRunner
    elif name == "shell":
        runner = ShellRunner
    elif name == "slurm":
        runner = SlurmRunner
    else:
        valid = ", ".join(valid_schedulers)
        raise ValueError(f"Unknown runner {name!r}, choose from direct, {valid}")
    tty.debug(f"Runner type = {runner.__name__}")
    return runner(session, **kwargs)
