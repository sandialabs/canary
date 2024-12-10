import argparse
import copy
import dataclasses
import json
import math
import os
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
from .schemas import resource_schema
from .schemas import test_schema
from .schemas import variables_schema

if TYPE_CHECKING:
    from ..test.atc import AbstractTestCase

section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "batch": batch_schema,
    "config": config_schema,
    "machine": machine_schema,
    "variables": variables_schema,
    "resource_pool": resource_schema,
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
          <resource name>:
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

    nvtest adopts a similar layout to work on multi-node systems by allowing for a list of
    objects (similar to ctest's ``local``) each with its own ``id``:

    .. code-block:: yaml

        resource_pool:
        - id: str
          <resource name>:
          - id: str
            slots: int

    For example, a machine having 2 nodes with 4 GPUs per node may have

    .. code-block:: yaml

        resource_pool:
        - id: "01"
          gpus:
          - id: "01"
            slots: 1
          - id: "02"
            slots: 1
          - id: "03"
            slots: 1
          - id: "04"
            slots: 1
        - id: "02"
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

    Resources are allocated from a global resource pool that is generated from the list of ``node``
    resource specifications.  A global-to-local mapping is maintained which maps the global resource
    ID understood by ``nvtest`` to the local resource ID given in the ``node`` resource spec.
    E.g., ``gid = map[type][(pid, lid)]``.

    Internal representation
    -----------------------

    Internally, the pool of resources is stored as a dictionary with layout (eg, for the example
    above):

    .. code-block:: python

       pool = [
         {
           "id": "01",
           "gpus": [
             {"id": "01", "slots": 1},
             {"id": "02", "slots": 1},
             {"id": "03", "slots": 1},
             {"id": "04", "slots": 1},
           ]
         }
       ]

    """

    def __init__(self, pool: list[dict[str, Any]] | None = None) -> None:
        self.map: dict[str, dict[tuple[str, str], int]] = {}
        self.pool: list[dict[str, Any]] = []
        self.types: set[str] = {"cpus", "gpus"}
        if pool:
            self.fill(pool)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self.fill(args[0])

    def fill(self, pool: list[dict[str, Any]]) -> None:
        self.clear()
        gids: dict[str, int] = {}
        for i, spec in enumerate(pool):
            pid = str(spec.pop("id", i))
            if "cpus" not in spec:
                raise TypeError(f"required resource 'cpus' not defined in pool instance {i}")
            if "gpus" not in spec:
                spec["gpus"] = []
            for type, instances in spec.items():
                self.types.add(type)
                for instance in instances:
                    lid = instance["id"]
                    gid = gids.setdefault(type, 0)
                    self.map.setdefault(type, {})[(pid, lid)] = gid
                    gids[type] += 1
            spec["id"] = pid
            self.pool.append(spec)

    def pinfo(self, item: str) -> Any:
        if item == "node_count":
            return len(self.pool)
        if item.endswith("_per_node"):
            key = item[:-9]
            for spec in self.pool:
                if key in spec:
                    return len(spec[key])
            return 0
        if item.endswith("_count"):
            key = item[:-6] + "s"
            count = 0
            for spec in self.pool:
                if key in spec:
                    count += len(spec[key])
            return 0
        raise KeyError(item)

    def getstate(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.pool)

    def gid(self, type: str, pid: str, lid: str) -> int:
        return self.map[type][(pid, lid)]

    def local_ids(self, type: str, arg_gid: int) -> tuple[str, str]:
        for key, gid in self.map[type].items():
            if arg_gid == gid:
                return key[0], key[1]
        raise KeyError((type, arg_gid))

    def min_nodes_required(self, obj: "AbstractTestCase") -> int:
        """Determine the number of nodes required by ``obj``"""
        node_count: int = 1
        for case in obj:
            required = case.required_resources()
            for group in required:
                for type in self.types:
                    count: int = 0
                    count_per_node = len(self.pool[0][type])
                    for item in group:
                        if item["type"] == type:
                            count += item["slots"]
                    if count_per_node and count:
                        node_count = max(math.ceil(count / count_per_node), node_count)
        return node_count

    def clear(self) -> None:
        self.map.clear()
        self.pool.clear()
        self.types.clear()

    def fill_uniform(self, *, node_count: int, cpus_per_node: int, **kwds: int) -> None:
        pool: list[dict[str, Any]] = []
        for i in range(node_count):
            spec: dict[str, Any] = {}
            for j in range(cpus_per_node):
                spec.setdefault("cpus", []).append({"id": str(j), "slots": 1})
            for name, count in kwds.items():
                if name.endswith("_per_node"):
                    for j in range(count):
                        spec.setdefault(name[:-9], []).append({"id": str(j), "slots": 1})
            spec["id"] = str(i)
            pool.append(spec)
        self.fill(pool)

    def validate(self, obj: "AbstractTestCase") -> None:
        """determine if the resources for this test are satisfiable"""
        required = obj.required_resources()
        try:
            save = copy.deepcopy(self.pool)
            for group in required:
                for item in group:
                    if item["type"] not in self.types:
                        t = item["type"]
                        msg = f"{obj}: required resource type {t!r} is not registered with nvtest"
                        raise ResourceUnsatisfiable(msg)
                    try:
                        self._get_from_pool(item["type"], item["slots"])
                    except ResourceUnavailable:
                        t = item["type"]
                        msg = f"{obj}: insufficient slots of {t!r} available"
                        raise ResourceUnsatisfiable(msg) from None
        finally:
            self.pool.clear()
            self.pool.extend(save)

    def _get_from_pool(self, type: str, slots: int) -> dict[str, Any]:
        for spec in self.pool:
            for name, instances in spec.items():
                if type == name:
                    for instance in sorted(instances, key=lambda x: x["slots"]):
                        if slots <= instance["slots"]:
                            instance["slots"] -= slots
                            gid = self.gid(type, spec["id"], instance["id"])
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
            save = copy.deepcopy(self.pool)
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
            self.pool.extend(save)
            raise
        if logging.LEVEL == logging.DEBUG:
            for type, n in totals.items():
                N = sum([_["slots"] for spec in self.pool for _ in spec[type]]) + n
                logging.debug(f"Acquiring {n} {type} from {N} available")
        obj.resources = resource_specs
        return

    def reclaim(self, obj: "AbstractTestCase") -> None:
        def _reclaim(type, rspec):
            pid, lid = self.local_ids(type, rspec["gid"])
            for spec in self.pool:
                if spec["id"] == pid:
                    for instance in spec[type]:
                        if instance["id"] == lid:
                            instance["slots"] += rspec["slots"]
                            return
            raise ValueError(f"Attempting to reclaim a resource whose ID is unknown: {rspec!r}")

        for resource in obj.resources:  # list[dict[str, list[dict]]]) -> None:
            for type, rspecs in resource.items():
                for rspec in rspecs:
                    _reclaim(type, rspec)
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


@dataclasses.dataclass
class Machine:
    cpu_count: int
    gpu_count: int

    def __post_init__(
        self,
    ) -> None:
        if self.cpu_count < 1:
            raise ValueError(f"cpu_count must be >= 1 ({self.cpu_count=})")
        if self.gpu_count < 0:
            raise ValueError(f"gpu_count must be >= 0 ({self.gpu_count=})")


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
    log_level: str = "INFO"
    _cache_dir: str | None = None
    _config_dir: str | None = None
    variables: Variables = dataclasses.field(default_factory=Variables)
    batch: Batch = dataclasses.field(default_factory=Batch)
    build: Build = dataclasses.field(default_factory=Build)
    options: argparse.Namespace = dataclasses.field(default_factory=argparse.Namespace)
    resource_pool: ResourcePool = dataclasses.field(default_factory=ResourcePool)

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
        kwds["resource_pool"].fill_uniform(
            node_count=1, cpus_per_node=m.cpu_count, gpus_per_node=m.gpu_count
        )

        return cls(**kwds)

    @property
    def cache_dir(self) -> str | None:
        if self._cache_dir is None:
            self._cache_dir = get_cache_dir()
        return self._cache_dir

    @property
    def config_dir(self) -> str | None:
        if self._config_dir is None:
            self._config_dir = get_config_dir()
        return self._config_dir

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
                if "_cache_dir" in items:
                    config["_cache_dir"] = items["_cache_dir"]
                if "_config_dir" in items:
                    config["_config_dir"] = items["_config_dir"]
                if "log_level" in items:
                    config["log_level"] = items["log_level"]
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
        if "_cache_dir" in data:
            self._cache_dir = data["_cache_dir"]
        if "_config_dir" in data:
            self._config_dir = data["_config_dir"]
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

        if args.config_file:
            file_data = self.read_config(args.config_file)
            for section, section_data in file_data.items():
                config_mods[section] = merge(config_mods.get(section, {}), section_data)

        if errors:
            raise ValueError("Stopping due to previous errors")

        for section, section_data in config_mods.items():
            obj = self if section == "config" else getattr(self, section)
            if hasattr(obj, "update"):
                obj.update(section_data)

        if n := getattr(args, "workers", None):
            if n > self.machine.cpu_count:
                raise ValueError(f"workers={n} > cpu_count={self.machine.cpu_count}")
        if b := getattr(args, "batch", None):
            if n := b.get("workers"):
                if n > self.machine.cpu_count:
                    raise ValueError(f"batch:workers={n} > cpu_count={self.machine.cpu_count}")

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variable NVTEST_LEVEL=1 to guard against this case.  But, if we are
        # running tests inside an existing test session and no batch arguments are given, we want
        # to use the original batch arguments.
        if os.getenv("NVTEST_LEVEL") == "1":
            args.batch = {}
        elif hasattr(args, "batch"):
            args.batch = args.batch or {}
            if args.batch.get("scheduler") == "null":
                # no batching
                args.batch.clear()
            else:
                old = getattr(self.options, "batch", None) or {}
                args.batch = merge(old, args.batch)
        elif getattr(self.options, "batch", None):
            args.batch = self.options.batch

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
            config[section] = validated[section]
        return config

    @staticmethod
    def config_file(scope: str) -> str | None:
        if scope == "global":
            config_dir = get_config_dir()
            if config_dir is not None:
                return os.path.join(config_dir, "config.yaml")
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
                d[key] = dataclasses.asdict(value)  # type: ignore
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


def get_cache_dir() -> str | None:
    cache_home: str
    if "NVTEST_CACHE_HOME" in os.environ:
        cache_home = os.environ["NVTEST_CACHE_HOME"]
    elif "XDG_CACHE_HOME" in os.environ:
        cache_home = os.environ["XDG_CACHE_HOME"]
    else:
        cache_home = os.path.expanduser("~/.cache")
    if cache_home in (os.devnull, "null"):
        return None
    cache_dir = os.path.join(cache_home, "nvtest")
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        return None
    file = os.path.join(cache_dir, "CACHEDIR.TAG")
    if not os.path.exists(file):
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a cache directory tag automatically created by nvtest.\n")
            fh.write(
                "# For information about cache directory tags see https://bford.info/cachedir/\n"
            )
    return cache_dir


def get_config_dir() -> str | None:
    config_home: str
    if "NVTEST_CONFIG_HOME" in os.environ:
        config_home = os.environ["NVTEST_CONFIG_HOME"]
    elif "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    if config_home in (os.devnull, "null"):
        return None
    config_dir = os.path.join(config_home, "nvtest")
    return config_dir


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


class ResourceUnsatisfiable(Exception):
    pass


class ResourceUnavailable(Exception):
    pass
