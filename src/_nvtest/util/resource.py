"""Classes and functions dealing with resource management"""

import math
import re
import shlex
from types import SimpleNamespace
from typing import Any
from typing import Optional
from typing import Union

from .. import config
from ..third_party.color import colorize
from .string import strip_quotes
from .time import time_in_seconds

Scalar = Union[str, int, float, None]
schedulers = ("slurm", "shell", None)


class ResourceInfo:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

        cpu_count = config.get("machine:cpu_count")
        self.data["session:cpu_count"] = cpu_count
        self.data["session:cpu_ids"] = list(range(cpu_count))

        gpu_count = config.get("machine:gpu_count")
        self.data["session:gpu_count"] = gpu_count
        self.data["session:gpu_ids"] = list(range(gpu_count))

        self.data["test:cpus"] = [0, cpu_count]
        self.data["test:gpus"] = gpu_count

        self.data["session:timeout"] = -1
        self.data["test:timeout"] = -1
        self.data["test:timeoutx"] = 1.0

        self.data["session:workers"] = -1
        self.meta: dict[str, int] = {}

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value
        print(key, value)
        print(self.meta)
        if key == "session:cpu_ids":
            if self.meta.get("session:cpu_count"):
                raise ValueError("session:cpu_ids and session:cpu_count are mutually exclusive")
            self.data["session:cpu_count"] = len(value)
        elif key == "session:cpu_count":
            if self.meta.get("session:cpu_ids"):
                raise ValueError("session:cpu_count and session:cpu_ids are mutually exclusive")
            self.data["session:cpu_ids"] = list(range(value))
        elif key == "session:gpu_ids":
            if self.meta.get("session:gpu_count"):
                raise ValueError("session:gpu_ids and session:gpu_count are mutually exclusive")
            self.data["session:gpu_count"] = len(value)
        elif key == "session:gpu_count":
            if self.meta.get("session:gpu_ids"):
                raise ValueError("session:gpu_count and session:gpu_ids are mutually exclusive")
            self.data["session:gpu_ids"] = list(range(value))
        self.meta[key] = self.meta.setdefault(key, 0) + 1

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __repr__(self):
        s = ", ".join(f"{key}={value}" for key, value in self.data.items())
        return f"ResourceInfo({s})"

    def asdict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for key, value in self.data.items():
            if value and value != -1:
                d[key[1:]] = value
        return d

    @staticmethod
    def parse(arg: str) -> tuple[str, Any]:
        if match := re.search(r"^session:(cpu_count|cpus|cores|processors)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session:cpu_count", int(raw))
        elif match := re.search(r"^session:cpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session:cpu_ids", ints)
        elif match := re.search(r"^session:gpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session:gpu_ids", ints)
        elif match := re.search(r"^session:workers[:=](\d+)$", arg):
            raw = match.group(1)
            return ("session:workers", int(raw))
        elif match := re.search(r"^session:(gpu_count|devices|gpus)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session:gpu_count", int(raw))
        elif match := re.search(r"^test:(devices|gpus)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("test:gpus", int(raw))
        elif match := re.search(r"^test:(cpus|cores|processors)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test:cpus", [0, int(raw)])
        elif match := re.search(r"^test:(cpus|cores|processors)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test:cpus", [int(raw), config.get("machine:cpu_count")])
        elif match := re.search(r"^test:(cpus|cores|processors)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test:cpus", [int(a), int(b)])
        elif match := re.search(r"^(session|test):timeout[:=](.*)$", arg):
            scope, raw = match.group(1), strip_quotes(match.group(2))
            return (f"{scope}:timeout", time_in_seconds(raw))
        elif match := re.search(r"^test:timeoutx[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("test:timeoutx", time_in_seconds(raw))
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")

    def set(self, key: str, value: Any) -> None:
        if key == "session:cpu_count":
            if value < 0:
                raise ValueError(f"session:cpu_count = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session cpu request exceeds machine cpu count")
        elif key == "session:gpu_count":
            if value < 0:
                raise ValueError(f"session:gpu_count = {value} < 0")
            elif value > config.get("machine:gpu_count"):
                raise ValueError("session gpu request exceeds machine gpu count")
        elif key == "session:workers":
            if value < 0:
                raise ValueError(f"session:workers = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session worker request exceeds machine cpu count")
        elif key == "test:gpus":
            if value < 0:
                raise ValueError(f"test:gpus = {value} < 0")
            elif value > config.get("machine:gpu_count"):
                raise ValueError("test gpu request exceeds machine gpu count")
            elif self["session:gpu_count"] > 0 and value > self["session:gpu_count"]:
                raise ValueError("test gpu request exceeds session gpu limit")
        elif key == "test:cpus":
            min_cpus, max_cpus = value
            if min_cpus > max_cpus:
                raise ValueError("test min cpus > test max cpus")
            elif min_cpus < 0:
                raise ValueError(f"test:cpus:{min_cpus} < 0")
            elif max_cpus < 0:
                raise ValueError(f"test:cpus:{max_cpus} < 0")
            elif max_cpus > config.get("machine:cpu_count"):
                raise ValueError("test max cpu request exceeds machine cpu count")
            elif self["session:cpu_count"] > 0 and max_cpus > self["session:cpu_count"]:
                raise ValueError("test cpu request exceeds session cpu limit")
        elif key == "session:cpu_ids":
            if not isinstance(value, list) and not all([isinstance(x, int) for x in value]):
                raise ValueError("session cpu ids must be a list of integers")
        elif key == "session:gpu_ids":
            if not isinstance(value, list) and not all([isinstance(x, int) for x in value]):
                raise ValueError("session gpu ids must be a list of integers")
        elif key not in ("test:timeout", "test:timeoutx", "session:timeout"):
            raise ValueError(f"unknown resource name: {key!r}")
        self[key] = value

    @staticmethod
    def cli_help(flag) -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        text = """\
Defines resources that are required by the test session and establishes limits
to the amount of resources that can be consumed. The %(r_arg)s argument is of
the form: ``%(r_form)s``.  The possible ``%(r_form)s`` settings are\n\n
• ``%(f)s session:workers=N``: Execute the test session asynchronously using a pool of at most N workers [default: auto]\n\n
• ``%(f)s session:cpu_count=N``: Occupy at most N cpu cores at any one time.\n\n
• ``%(f)s session:gpu_count=N``: Occupy at most N gpus at any one time.\n\n
• ``%(f)s session:timeout=T``: Set a timeout on test session execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: 60m]\n\n
• ``%(f)s test:cpus=[n:]N``: Skip tests requiring less than n and more than N cpu cores [default: 0 and machine cpu count]\n\n
• ``%(f)s test:gpus=N``: Skip tests requiring more than N gpus.\n\n
• ``%(f)s test:timeout=T``: Set a timeout on any single test execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s)\n\n
• ``%(f)s test:timeoutx=R``: Set a timeout multiplier for all tests [default: 1.0]\n\n
""" % {"f": flag, "r_form": bold("scope:type=value"), "r_arg": bold(f"{flag} resource")}
        return text


class BatchInfo:
    def __init__(self) -> None:
        self._length: Optional[float] = None
        self._count: Optional[int] = None
        self._scheduler: Optional[str] = None
        self._workers: Optional[int] = None
        self._args: list[str] = []

    def __repr__(self):
        s = ", ".join(f"{key[1:]}={value}" for key, value in vars(self).items())
        return f"BatchInfo({s})"

    def asdict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for key, value in vars(self).items():
            if value:
                d[key[1:]] = value
        return d

    @staticmethod
    def parse(arg: str) -> tuple[str, Any]:
        if match := re.search(r"^length[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            length = time_in_seconds(raw)
            if length <= 0:
                raise ValueError("batch length <= 0")
            return ("length", time_in_seconds(raw))
        elif match := re.search(r"^(count|workers)[:=](\d+)$", arg):
            type, raw = match.groups()
            return (type, int(raw))
        elif match := re.search(r"^scheduler[:=](\w+)$", arg):
            raw = match.group(1)
            return ("scheduler", str(raw))
        elif match := re.search(r"^args[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("args", shlex.split(raw))
        else:
            raise ValueError(f"invalid batch arg: {arg!r}")

    @property
    def args(self) -> list[str]:
        return self._args

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

    def set(self, key: str, value: Any) -> None:
        if key == "length":
            self.length = float(value)
        elif key == "count":
            self.count = int(value)
        elif key == "workers":
            self.workers = int(value)
        elif key == "scheduler":
            self.scheduler = str(value)
        elif key == "args":
            if isinstance(value, str):
                value = shlex.split(value)
            self.args.extend(value)
        else:
            raise ValueError(f"unknown batch resource name: {key!r}")

    @staticmethod
    def cli_help(flag) -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        resource_help = """\
Defines how to batch test cases. The %(r_arg)s argument is of the form: ``%(r_form)s``.
The possible possible ``%(r_form)s`` settings are\n\n
• ``%(f)s count=N``: Execute tests in N batches.\n\n
• ``%(f)s length=T``: Execute tests in batches having runtimes of approximately T seconds.  [default: 30 min]\n\n
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


def ilist(arg: str) -> list[int]:
    """Convert comma separated list of integers in `arg` into a list of int

    List can also contain ranges.

    Examples:

    >>> ilist("1,2,3")
    [1, 2, 3]
    >>> ilist("1,2,3,5-9")
    [1, 2, 3, 5, 6, 7, 8, 9]

    """
    arg_wo_space = re.sub(r"[ \t]", "", arg)
    if re.search(r"^\d+$", arg_wo_space):
        return [int(arg_wo_space)]
    if re.search(r"^\d+(,\d+)*$", arg_wo_space):
        return [int(_) for _ in arg_wo_space.split(",") if _.split()]
    if re.search(r"^(\d+(-\d_)?)(,\d+(-\d+)?)*$", arg_wo_space):
        ints: list[int] = []
        for x in arg_wo_space.split(","):
            if "-" in x:
                a, b = [int(_) for _ in x.split("-") if _.split()]
                ints.extend(range(a, b + 1))
            else:
                ints.append(int(x))
        return ints
    raise ValueError(f"{arg!r}: unknown integer list representation")
