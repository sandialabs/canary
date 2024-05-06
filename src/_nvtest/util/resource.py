"""Classes and functions dealing with resource management"""

import math
import shlex
from types import SimpleNamespace
from typing import Optional
from typing import Union

from .. import config
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

        self["session:workers"] = -1
        self["batch:workers"] = -1

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
            valid_types = ("cpus", "devices", "timeout")
        elif scope == "session":
            valid_types = ("workers", "cpus", "devices", "timeout")
        elif scope == "batch":
            valid_types = ("workers",)
        else:
            raise ValueError(f"invalid resource scope {scope!r}")
        if type not in valid_types:
            raise ValueError(f"{type} is an invalid {scope} resource")

        if isinstance(value, str):
            if type == "timeout":
                value = time_in_seconds(value, negatives=True)
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
        elif key == "batch:workers":
            if value < 0:
                raise ValueError(f"batch:workers = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session worker request exceeds machine cpu count")

        self[key] = value


class BatchInfo:
    def __init__(self) -> None:
        self._limit: Optional[float] = None
        self._count: Optional[int] = None
        self._scheduler: Optional[str] = None
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
            if self.limit is not None:
                raise ValueError("batch count and batch limit are mutually exclusive")
            self._count = int(arg)

    @property
    def limit(self) -> Optional[float]:
        return self._limit

    @limit.setter
    def limit(self, arg: Scalar) -> None:
        if arg is not None:
            if self.count is not None:
                raise ValueError("batch count and batch limit are mutually exclusive")
            self._limit = time_in_seconds(arg)

    def set(self, key: str, value: Scalar):
        if key == "limit":
            self.limit = value  # type: ignore
        elif key == "count":
            self.count = value  # type: ignore
        elif key == "scheduler":
            if not isinstance(value, str):
                raise ValueError("expected scheduler to be of type str")
            self.scheduler = value
        elif key == "args":
            self.args.extend(shlex.split(value))
        else:
            raise ValueError(f"{key}: unknown attribute name")


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
