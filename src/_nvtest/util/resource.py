"""Classes and functions dealing with resource management"""

import math
import shlex
from types import SimpleNamespace
from typing import Optional
from typing import Union

from .. import config
from ..third_party.color import colorize
from .time import time_in_seconds

Scalar = Union[str, int, float, None]
Number = Union[int, float]
schedulers = ("slurm", "shell", None)


class ResourceInfo:
    def __init__(self) -> None:
        self.data: dict[str, Number] = {}

        cpu_count = config.get("machine:cpu_count")
        self["session:cpus"] = cpu_count
        self["test:cpus"] = cpu_count

        device_count = config.get("machine:device_count")
        self["session:devices"] = device_count
        self["test:devices"] = device_count

        self["session:timeout"] = -1
        self["test:timeout"] = -1
        self["test:timeoutx"] = 1.0

        self["session:workers"] = -1

    def __setitem__(self, key: str, value: Number) -> None:
        self.data[key] = value

    def __getitem__(self, key: str) -> Number:
        return self.data[key]

    def __repr__(self):
        s = ", ".join(f"{key}={value}" for key, value in self.data.items())
        return f"ResourceInfo({s})"

    def set(self, scope: str, type: str, value: Union[Number, str]) -> None:
        valid_types: tuple
        if scope == "test":
            valid_types = ("cpus", "devices", "timeout", "timeoutx")
        elif scope == "session":
            valid_types = ("workers", "cpus", "devices", "timeout")
        else:
            raise ValueError(f"invalid resource scope {scope!r}")
        if type not in valid_types:
            raise ValueError(f"{type} is an invalid {scope} resource")

        if isinstance(value, str):
            if type == "timeout":
                value = time_in_seconds(value, negatives=True)
            elif type == "timeoutx":
                value = float(value)
            else:
                value = int(value)
        assert isinstance(value, (int, float))

        key = f"{scope}:{type}"

        if key == "session:cpus":
            if value < 0:
                raise ValueError(f"session:cpus = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session cpu request exceeds machine cpu count")
        elif key == "session:devices":
            if value < 0:
                raise ValueError(f"session:devices = {value} < 0")
            elif value > config.get("machine:device_count"):
                raise ValueError("session device request exceeds machine device count")
        elif key == "session:workers":
            if value < 0:
                raise ValueError(f"session:workers = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session worker request exceeds machine cpu count")
        elif key == "test:cpus":
            if value < 0:
                raise ValueError(f"test:cpus = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("test cpu request exceeds machine cpu count")
            elif self["session:cpus"] > 0 and value > self["session:cpus"]:
                raise ValueError("test cpu request exceeds session cpu limit")
        elif key == "test:devices":
            if value < 0:
                raise ValueError(f"test:devices = {value} < 0")
            elif value > config.get("machine:device_count"):
                raise ValueError("test device request exceeds machine device count")
            elif self["session:devices"] > 0 and value > self["session:devices"]:
                raise ValueError("test device request exceeds session device limit")

        self[key] = value

    @staticmethod
    def cli_help(flag) -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        text = """\
Defines resources that are required by the test session and establishes limits
to the amount of resources that can be consumed. The %(r_arg)s argument is of
the form: ``%(r_form)s``.  The possible ``%(r_form)s`` settings are\n\n
• ``%(f)s session:workers:N``: Execute the test session asynchronously using a pool of at most N workers [default: auto]\n\n
• ``%(f)s session:cpus:N``: Occupy at most N cpu cores at any one time.\n\n
• ``%(f)s session:devices:N``: Occupy at most N devices at any one time.\n\n
• ``%(f)s session:timeout:T``: Set a timeout on test session execution in seconds (accepts human readable expressions like 1s, 1 hr, 2 hrs, etc) [default: 60 min]\n\n
• ``%(f)s test:cpus:N``: Skip tests requiring more than N cpu cores.\n\n
• ``%(f)s test:devices:N``: Skip tests requiring more than N devices.\n\n
• ``%(f)s test:timeout:T``: Set a timeout on any single test execution in seconds (accepts human readable expressions like 1s, 1 hr, 2 hrs, etc) [default: 60 min]\n\n
• ``%(f)s test:timeoutx:R``: Set a timeout multiplier for all tests [default: 1.0]\n\n
""" % {"f": flag, "r_form": bold("scope:type:value"), "r_arg": bold(f"{flag} resource")}
        return text


class BatchInfo:
    def __init__(self) -> None:
        self._length: Optional[float] = None
        self._count: Optional[int] = None
        self._scheduler: Optional[str] = None
        self._workers: Optional[int] = None
        self.args: list[str] = []

    def __repr__(self):
        s = ", ".join(f"{key[1:]}={value}" for key, value in vars(self).items())
        return f"BatchInfo({s})"

    @property
    def scheduler(self) -> Optional[str]:
        return self._scheduler

    @scheduler.setter
    def scheduler(self, arg: Optional[str]) -> None:
        if arg is not None:
            if arg not in schedulers:
                raise ValueError(f"unsupported scheduler: {arg!r}")
            self._scheduler = arg

    @property
    def count(self) -> Optional[int]:
        return self._count

    @count.setter
    def count(self, arg: Scalar) -> None:
        if arg is not None:
            if self.length is not None:
                raise ValueError("batch count and batch length are mutually exclusive")
            self._count = int(arg)

    @property
    def length(self) -> Optional[float]:
        return self._length

    @length.setter
    def length(self, arg: Scalar) -> None:
        if arg is not None:
            if self.count is not None:
                raise ValueError("batch count and batch length are mutually exclusive")
            self._length = time_in_seconds(arg)

    @property
    def workers(self) -> Optional[int]:
        return self._workers

    @workers.setter
    def workers(self, arg: Scalar) -> None:
        if arg is not None:
            workers = int(arg)
            if workers < 0:
                raise ValueError(f"batch workers:{arg} < 0")
            elif workers > config.get("machine:cpu_count"):
                raise ValueError("batch worker request exceeds machine cpu count")
            self._workers = workers

    def set(self, key: str, value: Scalar):
        if key in ("length", "limit"):
            self.length = value  # type: ignore
        elif key == "count":
            self.count = value  # type: ignore
        elif key == "workers":
            self.workers = value  # type: ignore
        elif key == "scheduler":
            if not isinstance(value, str):
                raise ValueError("expected scheduler to be of type str")
            self.scheduler = value
        elif key == "args":
            if not isinstance(value, str):
                raise ValueError("expected scheduler args to be of type str")
            self.args.extend(shlex.split(value))
        else:
            raise ValueError(f"{key}: unknown attribute name")

    @staticmethod
    def cli_help(flag) -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        resource_help = """\
Defines how to batch test cases. The %(r_arg)s argument is of the form: ``%(r_form)s``.
The possible possible ``%(r_form)s`` settings are\n\n
• ``%(f)s count:N``: Execute tests in N batches.\n\n
• ``%(f)s length:T``: Execute tests in batches having runtimes of approximately T seconds.  [default: 30 min]\n\n
• ``%(f)s scheduler:S``: Use scheduler 'S' to run the test batches.\n\n
• ``%(f)s workers:N``: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• ``%(f)s args:A``: Any additional args 'A' are passed directly to the scheduler, for example,
  ``%(f)s args:--account=ABC`` will pass ``--account=ABC`` to the scheduler
""" % {"f": flag, "r_form": bold("type:value"), "r_arg": bold(f"{flag} resource")}
        return resource_help


def calculate_allocations(tasks: int) -> SimpleNamespace:
    """Performs basic resource calculations"""
    cores_per_socket = config.get("machine:cores_per_socket")
    sockets_per_node = config.get("machine:sockets_per_node") or 1
    cores_per_node = cores_per_socket * sockets_per_node
    tasks_per_node = min(tasks, cores_per_node)
    nodes = int(math.ceil(tasks / cores_per_node))
    ns = SimpleNamespace(
        cores_per_node=cores_per_node,
        sockets_per_node=sockets_per_node,
        nodes=nodes,
        tasks_per_node=tasks_per_node,
        cpus_per_task=1,
    )
    return ns
