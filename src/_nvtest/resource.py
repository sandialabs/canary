import argparse
import re
import shlex
from typing import Any
from typing import Optional

from . import config
from .third_party.color import colorize
from .util.string import ilist
from .util.string import strip_quotes
from .util.time import time_in_seconds


class ResourceHandler:
    def __init__(self) -> None:
        node_count = config.get("machine:node_count")
        cpus_per_node = config.get("machine:cpus_per_node")
        gpus_per_node = config.get("machine:gpus_per_node")
        cpu_count = cpus_per_node * node_count
        gpu_count = gpus_per_node * node_count
        self.data: dict[str, Any] = {
            "session": {
                "cpu_count": cpu_count,
                "cpu_ids": list(range(cpu_count)),
                "gpu_count": gpu_count,
                "gpu_ids": list(range(gpu_count)),
                "node_count": node_count,
                "node_ids": list(range(node_count)),
                "workers": -1,
                "timeout": None,
                "meta": {},
            },
            "test": {
                "cpu_count": [1, cpu_count],
                "gpu_count": [0, gpu_count],
                "node_count": [1, node_count],
                "timeout": None,
                "timeoutx": 1.0,
            },
            "batch": {
                "length": None,
                "count": None,
                "scheduler": None,
                "scheduler_args": [],
                "workers": None,
                "batched": False,
            },
        }

    def __getitem__(self, path: str) -> Any:
        scope, type = path.split(":")
        return self.data[scope][type]

    def get(self, path: str, default: Optional[Any] = None) -> Optional[Any]:
        scope, type = path.split(":")
        if scope not in self.data:
            raise ValueError(f"{scope!r} is not a valid ResourceHandler scope")
        scoped_data = self.data[scope]
        try:
            return scoped_data[type]
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
        node_count = config.get("machine:node_count")
        cpus_per_node = config.get("machine:cpus_per_node")
        gpus_per_node = config.get("machine:gpus_per_node")
        cpu_count = node_count * cpus_per_node
        gpu_count = node_count * gpus_per_node
        match (scope, type):
            case ("session", "cpu_count"):
                if not isinstance(value, int):
                    raise ValueError("session cpu count must be an integer")
                if value <= 0:
                    raise ValueError(f"session:cpu_count = {value} <= 0")
                elif value > cpu_count:
                    raise ValueError("session cpu request exceeds machine cpu count")
                if self.data["session"]["meta"].get("cpu_ids"):
                    raise ValueError(
                        "session:cpu_count and session:cpu_ids are mutually exclusive"
                    )
                self.data["session"]["meta"]["cpu_count"] = 1
                self.data["session"]["cpu_ids"] = list(range(value))

            case ("session", "cpu_ids"):
                if not isinstance(value, list) and not all([isinstance(x, int) for x in value]):
                    raise ValueError("session cpu ids must be a list of integers")
                if self.data["session"]["meta"].get("cpu_count"):
                    raise ValueError(
                        "session:cpu_ids and session:cpu_count are mutually exclusive"
                    )
                if len(value) == 0:
                    raise ValueError("len(session:cpu_ids) = 0")
                elif len(value) > cpu_count:
                    raise ValueError("number of session cpu ids exceeds machine cpu count")
                self.data["session"]["meta"]["cpu_ids"] = 1
                self.data["session"]["cpu_count"] = len(value)

            case ("session", "gpu_count"):
                if not isinstance(value, int):
                    raise ValueError("session gpu count must be an integer")
                if value < 0:
                    raise ValueError(f"session:gpu_count = {value} < 0")
                elif value > gpu_count:
                    raise ValueError("session gpu request exceeds machine gpu count")
                if self.data["session"]["meta"].get("gpu_ids"):
                    raise ValueError(
                        "session:gpu_count and session:gpu_ids are mutually exclusive"
                    )
                self.data["session"]["meta"]["gpu_count"] = 1
                self.data["session"]["gpu_ids"] = list(range(value))

            case ("session", "gpu_ids"):
                if not isinstance(value, list) and not all([isinstance(x, int) for x in value]):
                    raise ValueError("session gpu ids must be a list of integers")
                if self.data["session"]["meta"].get("gpu_count"):
                    raise ValueError(
                        "session:gpu_ids and session:gpu_count are mutually exclusive"
                    )
                if len(value) == 0:
                    raise ValueError("len(session:gpu_ids) = 0")
                elif len(value) > gpu_count:
                    raise ValueError("number of session gpu ids exceeds machine gpu count")
                self.data["session"]["meta"]["gpu_ids"] = 1
                self.data["session"]["gpu_count"] = len(value)

            case ("session", "workers"):
                if value < 0:
                    raise ValueError(f"session:workers = {value} < 0")
                elif value > cpu_count:
                    raise ValueError("session worker request exceeds machine cpu count")

            case ("session", "timeout"):
                pass

            # --- test resources
            case ("test", "cpu_count"):
                if isinstance(value, int):
                    value = [0, value]
                min_cpus, max_cpus = value
                if max_cpus is None:
                    max_cpus = self.data["session"]["cpu_count"]
                if min_cpus > max_cpus:
                    raise ValueError("test min cpus > test max cpus")
                elif min_cpus < 1:
                    raise ValueError(f"test:min_cpus = {min_cpus} < 1")
                elif max_cpus < 1:
                    raise ValueError(f"test:max_cpus = {max_cpus} < 1")
                elif max_cpus > cpu_count:
                    raise ValueError("test max cpu request exceeds machine cpu count")
                elif self["session:cpu_count"] > 1 and max_cpus > self["session:cpu_count"]:
                    raise ValueError("test cpu request exceeds session cpu limit")
                value = [min_cpus, max_cpus]

            case ("test", "gpu_count"):
                if isinstance(value, int):
                    value = [0, value]
                min_gpus, max_gpus = value
                if max_gpus is None:
                    max_gpus = self.data["session"]["gpu_count"]
                if min_gpus > max_gpus:
                    raise ValueError("test min gpus > test max gpus")
                elif min_gpus < 0:
                    raise ValueError(f"test:min_gpus = {min_gpus} < 0")
                elif max_gpus < 0:
                    raise ValueError(f"test:max_gpus = {max_gpus} < 0")
                elif max_gpus > gpu_count:
                    raise ValueError("test max gpu request exceeds machine gpu count")
                elif self["session:gpu_count"] > 0 and max_gpus > self["session:gpu_count"]:
                    raise ValueError("test gpu request exceeds session gpu limit")
                value = [min_gpus, max_gpus]

            case ("test", "node_count"):
                if isinstance(value, int):
                    value = [0, value]
                min_nodes, max_nodes = value
                if max_nodes is None:
                    max_nodes = self.data["session"]["cpu_count"]
                if min_nodes > max_nodes:
                    raise ValueError("test min nodes > test max nodes")
                elif min_nodes < 1:
                    raise ValueError(f"test:min_nodes = {min_nodes} < 1")
                elif max_nodes < 1:
                    raise ValueError(f"test:max_nodes = {max_nodes} < 1")
                elif max_nodes > config.get("machine:node_count"):
                    raise ValueError("test max node request exceeds machine node count")
                value = [min_nodes, max_nodes]

            case ("test", "timeout"):
                pass

            case ("test", "timeoutx"):
                if value <= 0.0:
                    raise ValueError("test timeoutx must be > 0")

            # --- batch resources
            case ("batch", "length"):
                if value <= 0.0:
                    raise ValueError("batch length must be > 0")
                if self.data["batch"]["count"] is not None:
                    raise ValueError("batch length and count are mutually exclusive")

            case ("batch", "count"):
                if value <= 0:
                    raise ValueError("batch count must be > 0")
                if self.data["batch"]["length"] is not None:
                    raise ValueError("batch count and length are mutually exclusive")

            case ("batch", "scheduler"):
                pass

            case ("batch", "workers"):
                if value < 0:
                    raise ValueError(f"batch:workers = {value} < 0")
                elif value > cpu_count:
                    raise ValueError("batch worker request exceeds machine cpu count")

            case ("batch", "scheduler_args"):
                if isinstance(value, str):
                    value = shlex.split(strip_quotes(value))
                value = self.data[scope][type] + list(value)

            case ("batch", "batched"):
                value = bool(value)

            case _:
                raise ValueError(f"unknown resource name: {path!r}")

        self.data[scope][type] = value
        if scope == "batch":
            self.data["batch"]["batched"] = True


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        rh = getattr(args, self.dest, None) or []
        if option_string == "-b":
            if not values.startswith("batch:"):
                values = f"batch:{values}"
        key, value = ResourceSetter.parse(values)
        rh.append((key, value))
        if key.startswith("batch:"):
            setattr(args, "batched_invocation", True)
        setattr(args, self.dest, rh)

    @staticmethod
    def help_page(flag: str) -> str:
        text = """\
Defines resources that are required by the test session and establishes limits
to the amount of resources that can be consumed. The %(r_arg)s argument is of
the form: %(r_form)s.  The possible %(r_form)s settings are\n\n
• session:workers=N: Execute the test session asynchronously using a pool of at most N workers [default: auto]\n\n
• session:cpu_count=N: Occupy at most N cpu cores at any one time.\n\n
• session:cpu_ids=L: Comma separated list of CPU ids available to the session, mutually exclusive with session:cpu_count.\n\n
• session:gpu_count=N: Occupy at most N gpus at any one time.\n\n
• session:gpu_ids=L: Comma separated list of GPU ids available to the session, mutually exclusive with session:gpu_count.\n\n
• session:timeout=T: Set a timeout on test session execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: 60m]\n\n
• test:cpu_count=[n:]N: Skip tests requiring less than n and more than N cpu cores [default: [1, machine:cpu_count]]\n\n
• test:gpu_count=[n:]N: Skip tests requiring less than n and more than N gpus [default: [0, machine:gpu_count]]\n\n
• test:node_count=[n:]N: Skip tests requiring less than n and more than N nodes [default: [1, machine:node_count]]\n\n
• test:timeout=T: Set a timeout on any single test execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s)\n\n
• test:timeoutx=R: Set a timeout multiplier for all tests [default: 1.0]\n\n
• batch:count=N: Execute tests in N batches.\n\n
• batch:length=T: Execute tests in batches having runtimes of approximately T seconds.  [default: 30 min]\n\n
• batch:scheduler=S: Submit test batches to scheduler 'S'.\n\n
• batch:workers=N: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• batch:scheduler_args=A: Any additional args 'A' are passed directly to the scheduler,
  for example, batch:scheduler_args=--account=ABC will pass --account=ABC to the scheduler
""" % {"r_form": _bold("scope:type=value"), "r_arg": _bold(f"{flag} resource")}
        return text

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
        elif match := re.search(r"^session:(gpu_count|gpus|devices)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session:gpu_count", int(raw))
        elif match := re.search(r"^test:(gpu_count|gpus|devices)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test:gpu_count", [1, int(raw)])
        elif match := re.search(r"^test:(gpu_count|gpus|devices)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test:gpu_count", [int(raw), None])
        elif match := re.search(r"^test:(gpu_count|gpus|devices)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test:gpu_count", [int(a), int(b)])
        elif match := re.search(r"^test:(cpu_count|cpus|cores|processors)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test:cpu_count", [1, int(raw)])
        elif match := re.search(r"^test:(cpu_count|cpus|cores|processors)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test:cpu_count", [int(raw), None])
        elif match := re.search(r"^test:(cpu_count|cpus|cores|processors)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test:cpu_count", [int(a), int(b)])
        elif match := re.search(r"^test:(node_count|nodes)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test:node_count", [1, int(raw)])
        elif match := re.search(r"^test:(node_count|nodes)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test:node_count", [int(raw), None])
        elif match := re.search(r"^test:(node_count|nodes)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test:node_count", [int(a), int(b)])
        elif match := re.search(r"^(session|test):timeout[:=](.*)$", arg):
            scope, raw = match.group(1), strip_quotes(match.group(2))
            return (f"{scope}:timeout", time_in_seconds(raw))
        elif match := re.search(r"^test:timeoutx[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("test:timeoutx", time_in_seconds(raw))
        elif match := re.search(r"^batch:length[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            length = time_in_seconds(raw)
            if length <= 0:
                raise ValueError("batch length <= 0")
            return ("batch:length", time_in_seconds(raw))
        elif match := re.search(r"^batch:(count|workers)[:=](\d+)$", arg):
            type, raw = match.groups()
            return (f"batch:{type}", int(raw))
        elif match := re.search(r"^batch:(runner|scheduler|type)[:=](\w+)$", arg):
            raw = match.group(2)
            return ("batch:scheduler", str(raw))
        elif match := re.search(r"^batch:(args|runner_args|scheduler_args)[:=](.*)$", arg):
            raw = strip_quotes(match.group(2))
            return ("batch:scheduler_args", shlex.split(raw))
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")


def setup_resource_handler(args: argparse.Namespace) -> None:
    """Set the resource handler

    There is a chicken/egg type problem when running nvtest:

    - nvtest uses hpc_connect to read machine information from the scheduler interface
    - nvtest needs machine information to do user-input validation and setup
    - but, hpc_connect cannot be initialized/setup until the user input is parsed to determine
      what scheduler is used.

    The solution is to store user inputs a ``ResourceSetter`` instance, which does not validate
    the user input.  The ``ResourceSetter`` is queried for the batch scheduler type which is used
    to initialize hpc_connect.  After hpc_connect is initialized, the ``ResourceHandler`` can be
    created from the ``ResourceSetter``.

    """
    args.rh = ResourceHandler()
    if resource_setter := getattr(args, "resource_setter", None):
        for path, value in resource_setter:
            args.rh.set(path, value)


def _bold(arg: str) -> str:
    return colorize("@*{%s}" % arg)
