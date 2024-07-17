import math
import shlex
from types import SimpleNamespace
from typing import Any
from typing import Optional

from . import config
from .util.string import strip_quotes


class ResourceHandler:
    def __init__(self) -> None:
        cpu_count = config.get("machine:cpu_count")
        gpu_count = config.get("machine:gpu_count")

        self.data: dict[str, Any] = {
            "session": {
                "cpu_count": cpu_count,
                "cpu_ids": list(range(cpu_count)),
                "gpu_count": gpu_count,
                "gpu_ids": list(range(gpu_count)),
                "workers": -1,
                "timeout": None,
                "meta": {},
            },
            "test": {
                "cpus": [0, cpu_count],
                "gpus": [0, gpu_count],
                "timeout": None,
                "timeoutx": 1.0,
            },
            "batch": {
                "length": None,
                "count": None,
                "scheduler": None,
                "workers": None,
                "args": [],
                "batched": False,
            },
        }

    def __getitem__(self, path: str) -> Any:
        scope, type = path.split(":")
        return self.data[scope][type]

    def get(self, path: str, default: Optional[Any] = None) -> Optional[Any]:
        scope, type = path.split(":")
        try:
            return self.data[scope][type]
        except KeyError:
            return default

    def __repr__(self) -> str:
        x: list[str] = []
        for scope in self.data:
            for type, value in self.data[scope].items():
                x.append(f"{scope}:{type}={value}")
        return f"ResourceHandler({', '.join(x)})"

    def set(self, path: str, value: Any) -> None:
        scope, type = path.split(":")

        # --- session resources
        if (scope, type) == ("session", "cpu_count"):
            if not isinstance(value, int):
                raise ValueError("session cpu count must be an integer")
            if value <= 0:
                raise ValueError(f"session:cpu_count = {value} <= 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session cpu request exceeds machine cpu count")
            if self.data["session"]["meta"].get("cpu_ids"):
                raise ValueError("session:cpu_count and session:cpu_ids are mutually exclusive")
            self.data["session"]["meta"]["cpu_count"] = 1
            self.data["session"]["cpu_ids"] = list(range(value))

        elif (scope, type) == ("session", "cpu_ids"):
            if not isinstance(value, list) and not all([isinstance(x, int) for x in value]):
                raise ValueError("session cpu ids must be a list of integers")
            if self.data["session"]["meta"].get("cpu_count"):
                raise ValueError("session:cpu_ids and session:cpu_count are mutually exclusive")
            if len(value) == 0:
                raise ValueError("len(session:cpu_ids) = 0")
            elif len(value) > config.get("machine:cpu_count"):
                raise ValueError("number of session cpu ids exceeds machine cpu count")
            self.data["session"]["meta"]["cpu_ids"] = 1
            self.data["session"]["cpu_count"] = len(value)

        elif (scope, type) == ("session", "gpu_count"):
            if not isinstance(value, int):
                raise ValueError("session gpu count must be an integer")
            if value < 0:
                raise ValueError(f"session:gpu_count = {value} < 0")
            elif value > config.get("machine:gpu_count"):
                raise ValueError("session gpu request exceeds machine gpu count")
            if self.data["session"]["meta"].get("gpu_ids"):
                raise ValueError("session:gpu_count and session:gpu_ids are mutually exclusive")
            self.data["session"]["meta"]["gpu_count"] = 1
            self.data["session"]["gpu_ids"] = list(range(value))

        elif (scope, type) == ("session", "gpu_ids"):
            if not isinstance(value, list) and not all([isinstance(x, int) for x in value]):
                raise ValueError("session gpu ids must be a list of integers")
            if self.data["session"]["meta"].get("gpu_count"):
                raise ValueError("session:gpu_ids and session:gpu_count are mutually exclusive")
            if len(value) == 0:
                raise ValueError("len(session:gpu_ids) = 0")
            elif len(value) > config.get("machine:gpu_count"):
                raise ValueError("number of session gpu ids exceeds machine gpu count")
            self.data["session"]["meta"]["gpu_ids"] = 1
            self.data["session"]["gpu_count"] = len(value)

        elif (scope, type) == ("session", "workers"):
            if value < 0:
                raise ValueError(f"session:workers = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("session worker request exceeds machine cpu count")

        elif (scope, type) == ("session", "timeout"):
            pass

        # --- test resources
        elif (scope, type) == ("test", "cpus"):
            min_cpus, max_cpus = value
            if isinstance(value, int):
                value = [0, value]
            if min_cpus > max_cpus:
                raise ValueError("test min cpus > test max cpus")
            elif min_cpus < 0:
                raise ValueError(f"test:min_cpus = {min_cpus} < 0")
            elif max_cpus < 0:
                raise ValueError(f"test:max_cpus = {max_cpus} < 0")
            elif max_cpus > config.get("machine:cpu_count"):
                raise ValueError("test max cpu request exceeds machine cpu count")
            elif self["session:cpu_count"] > 0 and max_cpus > self["session:cpu_count"]:
                raise ValueError("test cpu request exceeds session cpu limit")

        elif (scope, type) == ("test", "gpus"):
            if isinstance(value, int):
                value = [0, value]
            min_gpus, max_gpus = value
            if min_gpus > max_gpus:
                raise ValueError("test min gpus > test max gpus")
            elif min_gpus < 0:
                raise ValueError(f"test:min_gpus = {min_gpus} < 0")
            elif max_gpus < 0:
                raise ValueError(f"test:max_gpus = {max_gpus} < 0")
            elif max_gpus > config.get("machine:gpu_count"):
                raise ValueError("test max gpu request exceeds machine gpu count")
            elif self["session:gpu_count"] > 0 and max_gpus > self["session:gpu_count"]:
                raise ValueError("test gpu request exceeds session gpu limit")

        elif (scope, type) == ("test", "timeout"):
            pass

        elif (scope, type) == ("test", "timeoutx"):
            if value <= 0.0:
                raise ValueError("test timeoutx must be > 0")

        # --- batch resources
        elif (scope, type) == ("batch", "length"):
            if value <= 0.0:
                raise ValueError("batch length must be > 0")
            if self.data["batch"]["count"] is not None:
                raise ValueError("batch length and count are mutually exclusive")

        elif (scope, type) == ("batch", "count"):
            if value <= 0:
                raise ValueError("batch count must be > 0")
            if self.data["batch"]["length"] is not None:
                raise ValueError("batch count and length are mutually exclusive")

        elif (scope, type) == ("batch", "scheduler"):
            pass

        elif (scope, type) == ("batch", "workers"):
            if value < 0:
                raise ValueError(f"batch:workers = {value} < 0")
            elif value > config.get("machine:cpu_count"):
                raise ValueError("batch worker request exceeds machine cpu count")

        elif (scope, type) == ("batch", "args"):
            if isinstance(value, str):
                value = shlex.split(strip_quotes(value))
            value = self.data[scope][type] + list(value)

        elif (scope, type) == ("batch", "batched"):
            value = bool(value)

        else:
            raise ValueError(f"unknown resource name: {path!r}")

        self.data[scope][type] = value
        if scope == "batch":
            self.data["batch"]["batched"] = True


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
