import argparse
import copy
import dataclasses
import json
import math
import os
import re
from string import Template
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Any
from typing import TextIO

import yaml

from ..third_party import color
from ..third_party.schema import Schema
from ..third_party.schema import SchemaError
from ..util import logging
from ..util.collections import merge
from . import _machine
from .schemas import batch_schema
from .schemas import build_schema
from .schemas import config_schema
from .schemas import machine_schema
from .schemas import test_schema
from .schemas import variables_schema

if TYPE_CHECKING:
    from ..atc import AbstractTestCase

section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "batch": batch_schema,
    "config": config_schema,
    "machine": machine_schema,
    "variables": variables_schema,
    "test": test_schema,
}

log_levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.TRACE)


class Variables(dict):
    """Dict subclass that updates os.environ"""

    def __setitem__(self, key: str, value: Any) -> None:
        if value is None:
            os.environ.pop(str(key), None)
        else:
            os.environ[str(key)] = str(value)
        super().__setitem__(key, value)

    def update(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError(f"Variables.update() expected at most 1 argument, got {len(args)}")
        other = dict(*args, **kwargs)
        for key in other:
            self[key] = other[key]

    def pop(self, key: Any, /, default: Any = None) -> Any:
        os.environ.pop(str(key), default)
        return super().pop(key, default)


class ResourcePool:
    """Class representing resources available on the computer

    Args:
      pool: The resource pool specification

    Resource specification
    ----------------------

    The specification for the resource pool is adopted from the ctest schema:

    .. code-block:: yaml

        local:
          str:
          - id: str
            slots: int

    For example, a machine with 4 GPUs may have

    .. code-block:: yaml

        local:
          gpus:
          - id: "01"
            slots: 1
          - id: "02"
            slots: 1
          - id: "03"
            slots: 1
          - id: "04"
            slots: 1

    nvtest adopts a similar layout to work on multi-node systems by allowing for a list of ``local``
    objects and giving each ``local`` object its own ``id``:

    .. code-block:: yaml

        resource_pool:
        - local:
            .id: str
            str:
            - id: str
              slots: int

    where ``local:id`` is the ID of the ith entry in ``pool``

    For example, a machine having 2 nodes with 4 GPUs per node may have

    .. code-block:: yaml

        resource_pool:
        - local:
            .id: "01"
            gpus:
            - .id: "01"
              slots: 1
            - id: "02"
              slots: 1
            - id: "03"
              slots: 1
            - id: "04"
              slots: 1
        - local:
            .id: "02"
            gpus:
            - id: "01"
                slots: 1
            - id: "02"
                slots: 1
            - id: "03"
                slots: 1
            - id: "04"
                slots: 1

    Resource allocation
    -------------------

    Resources are allocated from a global resource pool that is generated from the list of ``local``
    resource specifications.  A global-to-local mapping is maintained which maps the global resource
    ID understood by ``nvtest`` to the local resource ID given in the ``local`` resource spec.
    E.g., ``gid = map[type][(pid, lid)]``.

    Internal representation
    -----------------------

    Internally, the pool of resources is stored as a dictionary with layout (eg, for the example
    above):

    .. code-block:: python

       pool = {
           "01": {
             "gpus": [
               {"id": "01", "slots": 1},
               {"id": "02", "slots": 1},
               {"id": "03", "slots": 1},
               {"id": "04", "slots": 1},
             ]
           }
       }

    """

    def __init__(self, pool: list[dict[str, Any]] | None = None) -> None:
        self.map: dict[str, dict[tuple[str, str], int]] = {}
        self.pool: dict[str, Any] = {}
        self.types: set[str] = set()
        if pool:
            self.fill(pool)

    def fill(self, pool: list[dict[str, Any]]) -> None:
        self.clear()
        gids: dict[str, int] = {}
        for i, item in enumerate(pool):
            local = item["local"]
            pid = str(local.pop(".id", i))
            for type, instances in local.items():
                if type.startswith("."):
                    continue
                self.types.add(type)
                for instance in instances:
                    lid = instance["id"]
                    gid = gids.setdefault(type, 0)
                    self.map.setdefault(type, {})[(pid, lid)] = gid
                    gids[type] += 1
            self.pool[pid] = local

    def pinfo(self, item: str) -> Any:
        if item == "node_count":
            return len(self.pool)
        if item.endswith("_per_node"):
            key = item[:-9]
            for local in self.pool.values():
                if key in local:
                    return len(local[key])
            return 0
        if item.endswith("_count"):
            key = item[:-6] + "s"
            count = 0
            for local in self.pool.values():
                if key in local:
                    count += len(local[key])
            return 0
        raise KeyError(item)

    def getstate(self) -> list[dict[str, Any]]:
        pool: list[dict[str, Any]] = []
        for pid, spec in self.pool.items():
            local = {".id": pid} | spec
            pool.append({"local": local})
        return pool

    def gid(self, type: str, pid: str, lid: str) -> int:
        return self.map[type][(pid, lid)]

    def local_ids(self, type: str, arg_gid: int) -> tuple[str, str]:
        for key, gid in self.map[type].items():
            if arg_gid == gid:
                return key[0], key[1]
        raise KeyError((type, arg_gid))

    def node_count(self, obj: "AbstractTestCase") -> int:
        """Determine the number of nodes required by ``obj``"""
        node_count: int = 1
        local = next(iter(self.pool.values()))
        if "cpus" in self.types:
            # always should be
            cpus_per_node = len(local["cpus"])
            cpus = max(_.cpus for _ in obj)
            node_count = math.ceil(cpus / cpus_per_node)
        if "gpus" in self.types:
            gpus_per_node = len(local["gpus"])
            gpus = max(_.gpus for _ in obj)
            node_count = max(math.ceil(gpus / gpus_per_node))
        return node_count

    def clear(self) -> None:
        self.map.clear()
        self.pool.clear()
        self.types.clear()

    def fill_uniform(self, *, node_count: int, cpus_per_node: int, **kwds: int) -> None:
        pool: list[dict[str, Any]] = []
        for i in range(node_count):
            local: dict[str, Any] = {}
            for j in range(cpus_per_node):
                local.setdefault("cpus", []).append({"id": str(j), "slots": 1})
            for name, count in kwds.items():
                if name.endswith("_per_node"):
                    for j in range(count):
                        local.setdefault(name[:-9], []).append({"id": str(j), "slots": 1})
            local[".id"] = str(i)
            pool.append({"local": local})
        self.fill(pool)

    def validate(self, obj: "AbstractTestCase") -> None:
        """determine if the resources for this test are satisfiable"""
        required = obj.required_resources()
        try:
            save = copy.deepcopy(self.pool)
            for group in required:
                for item in group:
                    if item["type"] not in self.types:
                        msg = f"resource type {item['type']!r} is not registered with nvtest"
                        raise ResourceUnsatisfiable(msg)
                    try:
                        self._get_from_pool(item["type"], item["slots"])
                    except ResourceUnavailable:
                        msg = f"insufficient slots of {item['type']!r} available"
                        raise ResourceUnsatisfiable(msg) from None
        finally:
            self.pool.clear()
            self.pool.update(save)

    def _get_from_pool(self, type: str, slots: int) -> dict[str, Any]:
        for pid, local in self.pool.items():
            for name, instances in local.items():
                if type == name:
                    for instance in sorted(instances, key=lambda x: x["slots"]):
                        if slots <= instance["slots"]:
                            instance["slots"] -= slots
                            gid = self.gid(type, pid, instance["id"])
                            return {"gid": gid, "slots": slots}
        raise ResourceUnavailable

    def acquire(self, obj: "AbstractTestCase") -> None:
        """Returns resources available to the test

        specs[i] = {<type>: [{'gid': <gid>, 'slots': <slots>}, ...], ... }

        """
        totals: dict[str, int] = {}
        required = obj.required_resources()
        if not required:
            raise ValueError(
                f"{obj}: no resources requested, a test should require at least 1 cpu"
            )
        resource_specs: list[dict[str, list[dict]]] = []
        try:
            saved = copy.deepcopy(self.pool)
            for group in required:
                # {type: [{gid: ..., slots: ...}]}
                spec: dict[str, list[dict]] = {}
                for item in group:
                    type, slots = item["type"], item["slots"]
                    if type not in self.types:
                        raise TypeError(f"unknown resource requirement type {type!r}")
                    r = self._get_from_pool(item["type"], item["slots"])
                    items = spec.setdefault(type, [])
                    items.append(r)
                    totals[type] = totals.get(type, 0) + slots
                resource_specs.append(spec)
        except Exception:
            self.pool.clear()
            self.pool.update(saved)
            raise
        if logging.LEVEL == logging.DEBUG:
            for type, n in totals.items():
                N = sum([_["slots"] for local in self.pool.values() for _ in local[type]]) + n
                logging.debug(f"Acquiring {n} {type} from {N} available")
        obj.resources = resource_specs
        return

    def reclaim(self, obj: "AbstractTestCase") -> None:
        for resource in obj.resources:  # list[dict[str, list[dict]]]) -> None:
            for type, items in resource.items():
                for item in items:
                    pid, lid = self.local_ids(type, item["gid"])
                    for instance in self.pool[pid][type]:
                        if instance["id"] == lid:
                            instance["slots"] += item["slots"]
                            break
                    else:
                        raise ValueError("Attempting to reclaim a resource whose ID is unknown")
        obj.resources.clear()


class Session:
    def __init__(
        self,
        *,
        work_tree: str | None = None,
        level: int | None = None,
        stage: str | None = None,
    ):
        self.work_tree = work_tree
        self.stage = stage
        self.level = level

    def __repr__(self) -> str:
        kwds = [f"{key.lstrip('_')}={value!r}" for key, value in vars(self).items()]
        return "{}({})".format(type(self).__name__, ", ".join(kwds))

    def getstate(self) -> dict[str, Any]:
        d = dict(vars(self))
        # these are set during the process
        d["stage"] = None
        d["level"] = None
        return d


@dataclasses.dataclass
class Test:
    timeout_fast: float = 120.0
    timeout_default: float = 5 * 60.0
    timeout_long: float = 15 * 60.0

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"Test.update() expected at most 1 argument, got {len(args)}")
        data = dict(*args) | kwargs
        for key, value in data.items():
            if key == "timeout":
                for k, v in value.items():
                    setattr(self, f"{key}_{k}", v)
            else:
                setattr(self, key, value)


class Machine:
    """Resources available on this machine

    Args:
      node_count: number of compute nodes
      *_per_node: number of **compute** '*' per node

    """

    def __init__(self, node_count: int, cpus_per_node: int, **kwds: int) -> None:
        if node_count < 1:
            raise ValueError(f"node count must be >= 1 ({node_count=})")
        self.node_count = node_count

        if cpus_per_node < 1:
            raise ValueError(f"cpus per node must be >= 1 ({cpus_per_node=})")
        self.cpus_per_node = cpus_per_node

        for key, value in kwds.items():
            if key.endswith("_per_node"):
                if value < 0:
                    raise ValueError(f"{key} must be > 0 ({key}={value})")
                setattr(self, key, value)
            else:
                raise TypeError(f"Machine() got an unexpected keyword argument {key!r}")

    def __repr__(self) -> str:
        return "Machine(%s)" % ", ".join(f"{k}={v}" for k, v in vars(self).items())

    def get(self, name: str) -> int:
        if hasattr(self, name):
            return getattr(self, name)
        if name.endswith("_per_node"):
            return 0
        raise TypeError(f"Machine.get() got an unexpected keyword argument {name!r}")

    def count(self, item: str) -> int:
        for key, value in self.__dict__.items():
            if key == f"{item}s_per_node" or key == f"{item}_per_node":
                return self.node_count * value
        return 0

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"Machine.update() expected at most 1 argument, got {len(args)}")
        data = dict(*args) | kwargs
        for key, value in data.items():
            if not re.search("(node_count)|([a-z_][a-z0-9_]*s_per_node)", key):
                raise TypeError(f"Machine.update() got an unexpected keyword argument {key!r}")
            setattr(self, key, value)

    def getstate(self) -> dict[str, int]:
        return dict(vars(self))


@dataclasses.dataclass(init=False, slots=True)
class System:
    node: str
    arch: str
    site: str
    host: str
    name: str
    platform: str
    os: SimpleNamespace

    def __init__(self, syscfg: dict | None = None) -> None:
        syscfg = syscfg or _machine.system_config()
        self.node = syscfg["node"]
        self.arch = syscfg["arch"]
        self.site = syscfg["site"]
        self.host = syscfg["host"]
        self.name = syscfg["name"]
        self.platform = syscfg["platform"]
        self.os = SimpleNamespace(**syscfg["os"])


@dataclasses.dataclass
class Compiler:
    vendor: str | None = None
    version: str | None = None
    cc: str | None = None
    cxx: str | None = None
    fc: str | None = None
    f77: str | None = None
    mpicc: str | None = None
    mpicxx: str | None = None
    mpifc: str | None = None
    mpif77: str | None = None


@dataclasses.dataclass
class Build:
    project: str | None = None
    type: str | None = None
    date: str | None = None
    build_directory: str | None = None
    source_directory: str | None = None
    compiler: Compiler = dataclasses.field(default_factory=Compiler)

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"Build.update() expected at most 1 argument, got {len(args)}")
        data = dict(*args) | kwargs
        if compiler := data.pop("compiler", None):
            for key, value in compiler.items():
                setattr(self.compiler, key, value)
        for key, value in data.items():
            setattr(self, key, value)


@dataclasses.dataclass
class Batch:
    duration: float = 30 * 60  # 30 minutes

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"Batch.update() expected at most 1 argument, got {len(args)}")
        data = dict(*args) | kwargs
        for key, value in data.items():
            setattr(self, key, value)


@dataclasses.dataclass
class Config:
    """Access to configuration values"""

    system: System
    machine: Machine
    session: Session
    test: Test
    invocation_dir: str = os.getcwd()
    debug: bool = False
    cache_runtimes: bool = True
    log_level: str = "INFO"
    variables: Variables = dataclasses.field(default_factory=Variables)
    batch: Batch = dataclasses.field(default_factory=Batch)
    build: Build = dataclasses.field(default_factory=Build)
    options: argparse.Namespace = dataclasses.field(default_factory=argparse.Namespace)
    resource_pool: ResourcePool = dataclasses.field(default_factory=ResourcePool)
    resource_params: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.resource_params:
            self.resource_params = ["cpus", "gpus"]

    @classmethod
    def factory(cls) -> "Config":
        """Create the configuration object"""
        self = cls.create()
        root = find_work_tree()
        if root:
            # If we are inside a session directory, then we want to restore its configuration
            # any changes create happens before setting command line options, so changes can still
            # be made to the restored configuration
            file = os.path.join(root, ".nvtest/config")
            if os.path.exists(file):
                with open(file) as fh:
                    self.restore_from_snapshot(fh)
            else:
                raise FileNotFoundError(file)
        return self

    @classmethod
    def create(cls) -> "Config":
        config: dict[str, Any] = {}
        cls.load_config("global", config)
        cls.load_config("local", config)

        kwds: dict[str, Any] = config.get("config", {})
        kwds["system"] = System()

        mc = _machine.machine_config()
        mc.update(config.get("machine", {}))
        kwds["machine"] = m = Machine(**mc)

        kwds["session"] = Session()

        kwds["test"] = Test()

        if "build" in kwds:
            c = kwds["build"]["compiler"]
            if "paths" in c:
                c.update(c.pop("paths"))
            kwds["build"]["compiler"] = Compiler(**c)
            kwds["build"] = Build(**kwds["build"])

        kwds["resource_pool"] = ResourcePool()
        kwds["resource_pool"].fill_uniform(**vars(m))

        return cls(**kwds)

    def update_resource_counts(self) -> None:
        kwds = vars(self.machine)
        self.resource_pool.fill_uniform(**kwds)

    def restore_from_snapshot(self, fh: TextIO) -> None:
        snapshot = json.load(fh)
        self.system = System(snapshot["system"])
        self.machine = Machine(**snapshot["machine"])
        self.variables.clear()
        self.variables.update(snapshot["variables"])
        self.session = Session(**snapshot["session"])
        self.test = Test(**snapshot["test"])
        compiler = Compiler(**snapshot["build"].pop("compiler"))
        self.build = Build(compiler=compiler, **snapshot["build"])
        self.resource_pool = ResourcePool()
        self.resource_pool.fill(snapshot["resource_pool"])
        for key, val in snapshot["config"].items():
            setattr(self, key, val)
        self.batch = Batch(**snapshot["batch"])

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variable NVTEST_LEVEL=1 to guard against this case.
        if os.getenv("NVTEST_LEVEL") == "1":
            # no batching (default)
            snapshot["options"].pop("batch", None)
        self.options = argparse.Namespace(**snapshot["options"])
        return

    def snapshot(self, fh: TextIO) -> None:
        snapshot = self.getstate()
        json.dump(snapshot, fh, indent=2)

    @classmethod
    def load_config(cls, scope: str, config: dict[str, Any]) -> None:
        file = cls.config_file(scope)
        if file is None or not os.path.exists(file):
            return
        file_data = cls.read_config(file)
        for key, items in file_data.items():
            if key == "config":
                if "debug" in items:
                    config["debug"] = bool(items["debug"])
                if "cache_runtimes" in items:
                    config["cache_runtimes"] = bool(items["cache_runtimes"])
                if "log_level" in items:
                    config["log_level"] = items["log_level"]
                if "resource_params" in items:
                    config["resource_params"] = list(items["resource_params"])
            elif key == "test":
                for name in ("fast", "long", "default"):
                    if name in items.get("timeout", {}):
                        config[f"test_timeout_{name}"] = items["timeout"][name]
            elif key == "machine":
                if "node_count" in items:
                    config["node_count"] = items["node_count"]
                if "cpus_per_node" in items:
                    config["cpus_per_node"] = items["cpus_per_node"]
                if "gpus_per_node" in items:
                    config["gpus_per_node"] = items["gpus_per_node"]
            elif key == "batch":
                if "duration" in items:
                    config["batch_duration"] = items["duration"]
                elif "length" in items:
                    config["batch_duration"] = items["length"]
            elif key in ("variables", "build"):
                config[key] = items

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"Config.update() expected at most 1 argument, got {len(args)}")
        data = dict(*args) | kwargs
        if "debug" in data:
            self.debug = boolean(data["debug"])
            if self.debug:
                self.log_level = logging.get_level_name(log_levels[3])
                logging.set_level(logging.DEBUG)
        if "cache_runtimes" in data:
            self.cache_runtimes = boolean(data["cache_runtimes"])
        if "resource_params" in data:
            self.resource_params = list(data["resource_params"])
        if "log_level" in data:
            self.log_level = data["log_level"].upper()
            level = logging.get_level(self.log_level)
            logging.set_level(level)

    def set_main_options(self, args: argparse.Namespace) -> None:
        logging.set_level(logging.INFO)
        if args.color is not None:
            color.set_color_when(args.color)

        if args.q or args.v:
            i = min(max(2 - args.q + args.v, 0), 4)
            self.log_level = logging.get_level_name(log_levels[i])
            logging.set_level(log_levels[i])

        if args.debug:
            self.debug = True
            self.log_level = logging.get_level_name(log_levels[3])
            logging.set_level(logging.DEBUG)

        if "session" in args.env_mods:
            self.variables.update(args.env_mods["session"])

        errors: int = 0
        config_mods = args.config_mods or {}
        for section, section_data in config_mods.items():
            if section not in section_schemas:
                errors += 1
                logging.error(f"Illegal config section: {section!r}")
                continue
            schema = section_schemas[section]
            config_mods[section] = schema.validate({section: section_data})[section]

        if errors:
            raise ValueError("Stopping due to previous errors")

        for section, section_data in config_mods.items():
            obj = self if section == "config" else getattr(self, section)
            if hasattr(obj, "update"):
                obj.update(section_data)

        if "machine" in config_mods:
            self.update_resource_counts()

        if n := getattr(args, "workers", None):
            if n > os.cpu_count():
                raise ValueError(f"workers={n} > cpu_count={os.cpu_count()}")
        if b := getattr(args, "batch", None):
            if n := b.get("workers"):
                if n > os.cpu_count():
                    raise ValueError(f"batch:workers={n} > cpu_count={os.cpu_count()}")

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variable NVTEST_LEVEL=1 to guard against this case.  But, if we are
        # running tests inside an existing test session and no batch arguments are given, we want
        # to use the original batch arguments.
        if os.getenv("NVTEST_LEVEL") == "1":
            # no batching
            args.batch = {}
        else:
            current = getattr(args, "batch", None) or {}
            old = getattr(self.options, "batch", None) or {}
            args.batch = merge(old, current)
        self.options = args

    @classmethod
    def read_config(cls, file: str) -> dict:
        with open(file) as fh:
            data = yaml.safe_load(fh)
        variables = dict(os.environ)

        # make variables available in other config sections
        if "variables" in data:
            section_data = data["variables"]
            for key, raw_value in section_data.items():
                value = expandvars(raw_value, variables)
                section_data[key] = str(safe_loads(value))
                variables[key] = section_data[key]

        for section in data:
            if section in ("variables",):
                continue
            for key, raw_value in data[section].items():
                value = expandvars(raw_value, variables)
                data[section][key] = value

        config: dict[str, Any] = {}
        # expand any keys given as a:b:c
        for section, section_data in data.items():
            if section not in section_schemas:
                logging.warning(f"ignoring unrecognized config section: {section}")
                continue
            schema = section_schemas[section]
            try:
                validated = schema.validate({section: section_data})
            except SchemaError as e:
                msg = f"Schema error encountered in {file}: {e.args[0]}"
                raise ValueError(msg) from None
            config[section] = validated
        return config

    @staticmethod
    def config_file(scope: str) -> str | None:
        if scope == "global":
            if "NVTEST_GLOBAL_CONFIG" in os.environ:
                return os.environ["NVTEST_GLOBAL_CONFIG"]
            elif "HOME" in os.environ:
                home = os.environ["HOME"]
                return os.path.join(home, ".nvtest")
        elif scope == "local":
            return os.path.abspath("./nvtest.yaml")
        return None

    @classmethod
    def save(cls, path: str, scope: str | None = None):
        file = cls.config_file(scope or "local")
        assert file is not None
        section, key, value = path.split(":")
        with open(file, "r") as fh:
            config = yaml.safe_load(fh)
        config.setdefault(section, {})[key] = safe_loads(value)
        with open(file, "w") as fh:
            yaml.dump(config, fh, default_flow_style=False)

    def getoption(self, key: str, default: Any = None) -> Any:
        """Compatibility with external tools"""
        option = getattr(self.options, key, None) or default
        return option

    def getstate(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for key, value in vars(self).items():
            if dataclasses.is_dataclass(value):
                d[key] = dataclasses.asdict(value)
                if key == "system":
                    d[key]["os"] = vars(d[key]["os"])
            elif hasattr(value, "getstate"):
                d[key] = value.getstate()
            elif isinstance(value, (argparse.Namespace, SimpleNamespace)):
                d[key] = vars(value)
            elif isinstance(value, Variables):
                d[key] = dict(value)
            else:
                d.setdefault("config", {})[key] = value
        return d

    def describe(self, section: str | None = None) -> str:
        state = self.getstate()
        if section is not None:
            state = {section: state[section]}
        return yaml.dump(state, default_flow_style=False)


def boolean(arg: Any) -> bool:
    if isinstance(arg, str):
        return arg.lower() in ("on", "1", "true", "yes")
    return bool(arg)


def find_work_tree(start: str | None = None) -> str | None:
    path = os.path.abspath(start or os.getcwd())
    tagfile = "SESSION.TAG"
    while True:
        if os.path.exists(os.path.join(path, tagfile)):
            return os.path.dirname(path)
        elif os.path.exists(os.path.join(path, ".nvtest", tagfile)):
            return path
        path = os.path.dirname(path)
        if path == os.path.sep:
            break
    return None


def expandvars(arg: Any, mapping: dict) -> Any:
    if isinstance(arg, list):
        for i, item in enumerate(arg):
            arg[i] = expandvars(item, mapping)
        return arg
    elif isinstance(arg, dict):
        for key, value in arg.items():
            arg[key] = expandvars(value, mapping)
        return arg
    elif isinstance(arg, str):
        t = Template(arg)
        return t.safe_substitute(mapping)
    return arg


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


class ResourceUnsatisfiable(Exception):
    pass


class ResourceUnavailable(Exception):
    pass
