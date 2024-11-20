import argparse
import dataclasses
import json
import os
from string import Template
from types import SimpleNamespace
from typing import Any
from typing import TextIO

from ..third_party.schema import Schema
from ..third_party.schema import SchemaError
from ..util import logging
from ..util.time import time_in_seconds
from . import _machine
from .schemas import batch_schema
from .schemas import build_schema
from .schemas import config_schema
from .schemas import machine_schema
from .schemas import test_schema
from .schemas import variables_schema

section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "batch": batch_schema,
    "config": config_schema,
    "machine": machine_schema,
    "variables": variables_schema,
    "test": test_schema,
}


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
            raise TypeError(f"update expected at most 1 argument, got {len(args)}")
        other = dict(*args, **kwargs)
        for key in other:
            self[key] = other[key]

    def pop(self, key: Any, /, default: Any = None) -> Any:
        os.environ.pop(str(key), default)
        return super().pop(key, default)


class Session:
    def __init__(
        self,
        *,
        node_count: int | None = None,
        node_ids: list[int] | None = None,
        cpu_count: int | None = None,
        cpu_ids: list[int] | None = None,
        gpu_count: int | None = None,
        gpu_ids: list[int] | None = None,
        timeout: float = -1.0,
        workers: int = -1,
        work_tree: str | None = None,
        level: int | None = None,
        stage: str | None = None,
    ):
        self._node_count: int
        self._node_ids: list[int]
        self._cpu_count: int
        self._cpu_ids: list[int]
        self._gpu_count: int = 0
        self._gpu_ids: list[int] = []

        if node_count is not None:
            if node_ids is not None and node_count != len(node_ids):
                raise ValueError("node_count and node_ids are mutually exclusive")
            self._node_count = node_count
            self._node_ids = list(range(node_count))
        elif node_ids is not None:
            if node_count is not None and node_count != len(node_ids):
                raise ValueError("node_count and node_ids are mutually exclusive")
            self._node_ids = list(node_ids)
            self._node_count = len(node_ids)
        else:
            raise TypeError("missing required argument: node_count")
        if cpu_count is not None:
            if cpu_ids is not None and cpu_count != len(cpu_ids):
                raise ValueError("cpu_count and cpu_ids are mutually exclusive")
            self._cpu_count = cpu_count
            self._cpu_ids = list(range(cpu_count))
        elif cpu_ids is not None:
            if cpu_count is not None and cpu_count != len(cpu_ids):
                raise ValueError("cpu_count and cpu_ids are mutually exclusive")
            self._cpu_ids = list(cpu_ids)
            self._cpu_count = len(cpu_ids)
        else:
            raise TypeError("missing required argument: cpu_count")
        if gpu_count is not None:
            if gpu_ids is not None and gpu_count != len(gpu_ids):
                raise ValueError("gpu_count and gpu_ids are mutually exclusive")
            self._gpu_count = gpu_count
            self._gpu_ids = list(range(gpu_count))
        elif gpu_ids is not None:
            if gpu_count is not None and gpu_count != len(gpu_ids):
                raise ValueError("gpu_count and gpu_ids are mutually exclusive")
            self._gpu_ids = list(gpu_ids)
            self._gpu_count = len(gpu_ids)
        else:
            raise TypeError("missing required argument: gpu_count")

        self.timeout = timeout
        self.workers = workers
        self.work_tree = work_tree
        self.stage = stage
        self.level = level

    def __repr__(self) -> str:
        kwds = [f"{key.lstrip('_')}={value!r}" for key, value in vars(self).items()]
        return "{}({})".format(type(self).__name__, ", ".join(kwds))

    def asdict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for name, value in vars(self).items():
            if name.startswith("_"):
                d[name[1:]] = value
            else:
                d[name] = value
        return d

    @property
    def node_count(self) -> int:
        return self._node_count

    @node_count.setter
    def node_count(self, arg: int) -> None:
        self._node_count = arg
        self._node_ids = list(range(arg))

    @property
    def node_ids(self) -> list[int]:
        return self._node_ids

    @node_ids.setter
    def node_ids(self, arg: list[int]) -> None:
        self._node_ids = list(arg)
        self._node_count = len(arg)

    @property
    def cpu_count(self) -> int:
        return self._cpu_count

    @cpu_count.setter
    def cpu_count(self, arg: int) -> None:
        self._cpu_count = arg
        self._cpu_ids = list(range(arg))

    @property
    def cpu_ids(self) -> list[int]:
        return self._cpu_ids

    @cpu_ids.setter
    def cpu_ids(self, arg: list[int]) -> None:
        self._cpu_ids = list(arg)
        self._cpu_count = len(arg)

    @property
    def gpu_count(self) -> int:
        return self._gpu_count

    @gpu_count.setter
    def gpu_count(self, arg: int) -> None:
        self._gpu_count = arg
        self._gpu_ids = list(range(arg))

    @property
    def gpu_ids(self) -> list[int]:
        return self._gpu_ids

    @gpu_ids.setter
    def gpu_ids(self, arg: list[int]) -> None:
        self._gpu_ids = list(arg)
        self._gpu_count = len(arg)


@dataclasses.dataclass
class Test:
    cpu_count: tuple[int, int]
    gpu_count: tuple[int, int]
    node_count: tuple[int, int]
    timeout: float = -1.0
    timeoutx: float = 1.0
    timeout_fast: float = 120.0
    timeout_default: float = 5 * 60.0
    timeout_long: float = 15 * 60.0


@dataclasses.dataclass
class Machine:
    """Resources available on this machine

    Args:
      node_count: number of compute nodes
      cpus_per_node: number of **compute** CPUs (MPI ranks) per node
      gpus_per_node: number of **compute** GPUs per node

    """

    node_count: int
    cpus_per_node: int
    gpus_per_node: int

    @property
    def cpu_count(self) -> int:
        return self.node_count * self.cpus_per_node

    @property
    def gpu_count(self) -> int:
        return self.node_count * self.gpus_per_node


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


@dataclasses.dataclass
class Batch:
    scheduler: str | None = None
    scheduler_args: list[str] | None = None
    workers: int | None = None
    length: float | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        if self.scheduler == "null" or os.getenv("NVTEST_BATCH_SCHEDULER") == "null":
            self.scheduler = None
            self.workers = None
            self.length = None
            self.count = None


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

        kwds["session"] = Session(
            node_count=m.node_count, cpu_count=m.cpu_count, gpu_count=m.gpu_count
        )

        kwds["test"] = Test(
            node_count=(1, m.node_count), cpu_count=(1, m.cpu_count), gpu_count=(0, m.gpu_count)
        )

        if "build" in kwds:
            c = kwds["build"]["compiler"]
            if "paths" in c:
                c.update(c.pop("paths"))
            kwds["build"]["compiler"] = Compiler(**c)
            kwds["build"] = Build(**kwds["build"])

        return cls(**kwds)

    def update_resource_counts(
        self,
        *,
        node_count: int | None = None,
        cpus_per_node: int | None = None,
        gpus_per_node: int | None = None,
    ) -> None:
        updated = any([cnt is not None for cnt in (node_count, cpus_per_node, gpus_per_node)])
        if not updated:
            return
        if node_count is not None:
            self.machine.node_count = node_count
        if cpus_per_node is not None:
            self.machine.cpus_per_node = cpus_per_node
        if gpus_per_node is not None:
            self.machine.gpus_per_node = gpus_per_node
        self.session.node_count = self.machine.node_count
        self.session.cpu_count = self.machine.cpu_count
        self.session.gpu_count = self.machine.gpu_count
        self.test.node_count = (1, self.machine.node_count)
        self.test.cpu_count = (1, self.machine.cpu_count)
        self.test.gpu_count = (0, self.machine.gpu_count)

    def validate(self):
        cpu_count = self.machine.cpu_count
        gpu_count = self.machine.gpu_count

        if self.session.cpu_count <= 0:
            raise ValueError(f"session:cpu_count = {self.session.cpu_count} <= 0")
        if self.session.cpu_count > cpu_count:
            raise ValueError("session cpu request exceeds machine cpu count")
        if self.session.gpu_count < 0:
            raise ValueError(f"session:gpu_count = {self.session.gpu_count} < 0")
        if self.session.gpu_count > gpu_count:
            raise ValueError("session gpu request exceeds machine gpu count")
        if self.session.workers > cpu_count:
            raise ValueError("session worker request exceeds machine cpu count")

        min_cpus, max_cpus = self.test.cpu_count
        if min_cpus > max_cpus:
            raise ValueError("test min cpus > test max cpus")
        if min_cpus < 1:
            raise ValueError(f"test:min_cpus = {min_cpus} < 1")
        if max_cpus < 1:
            raise ValueError(f"test:max_cpus = {max_cpus} < 1")
        if max_cpus > cpu_count:
            raise ValueError("test max cpu request exceeds machine cpu count")
        if self.session.cpu_count > 1 and max_cpus > self.session.cpu_count:
            raise ValueError("test cpu request exceeds session cpu limit")

        min_gpus, max_gpus = self.test.gpu_count
        if min_gpus > max_gpus:
            raise ValueError("test min gpus > test max gpus")
        if min_gpus < 0:
            raise ValueError(f"test:min_gpus = {min_gpus} < 0")
        if max_gpus < 0:
            raise ValueError(f"test:max_gpus = {max_gpus} < 0")
        if max_gpus > gpu_count:
            raise ValueError("test max gpu request exceeds machine gpu count")
        if self.session.gpu_count > 0 and max_gpus > self.session.gpu_count:
            raise ValueError("test gpu request exceeds session gpu limit")

        min_nodes, max_nodes = self.test.node_count
        if min_nodes > max_nodes:
            raise ValueError("test min nodes > test max nodes")
        if min_nodes < 1:
            raise ValueError(f"test:min_nodes = {min_nodes} < 1")
        if max_nodes < 1:
            raise ValueError(f"test:max_nodes = {max_nodes} < 1")
        if max_nodes > self.machine.node_count:
            raise ValueError("test max node request exceeds machine node count")

        if self.test.timeoutx <= 0.0:
            raise ValueError("test timeoutx must be > 0")

        # --- batch resources
        if self.batch.length and self.batch.length <= 0.0:
            raise ValueError("batch length must be > 0")
        if self.batch.count and self.batch.count <= 0:
            raise ValueError("batch count must be > 0")
        if self.batch.workers is not None and self.batch.workers > cpu_count:
            raise ValueError("batch worker request exceeds machine cpu count")

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
        self.options = argparse.Namespace(**snapshot["options"])
        for key, val in snapshot["config"].items():
            setattr(self, key, val)

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variables NVTEST_BATCH_SCHEDULER=null to guard against this case.
        if os.getenv("NVTEST_BATCH_SCHEDULER") == "null":
            # no batching (default)
            self.batch = Batch()
        else:
            self.batch = Batch(**snapshot["batch"])
        return

    def snapshot(self, fh: TextIO) -> None:
        snapshot: dict[str, Any] = {}
        snapshot["system"] = dataclasses.asdict(self.system)
        snapshot["system"]["os"] = vars(snapshot["system"]["os"])
        snapshot["machine"] = dataclasses.asdict(self.machine)
        snapshot["variables"] = dict(self.variables)
        snapshot["session"] = self.session.asdict()
        snapshot["test"] = dataclasses.asdict(self.test)
        snapshot["batch"] = dataclasses.asdict(self.batch)
        snapshot["build"] = dataclasses.asdict(self.build)
        snapshot["options"] = vars(self.options)
        config = snapshot.setdefault("config", {})
        config["invocation_dir"] = self.invocation_dir
        config["debug"] = self.debug
        config["cache_runtimes"] = self.cache_runtimes
        config["log_level"] = self.log_level
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
            elif key == "test":
                for key in ("fast", "long", "default"):
                    if key in items.get("timeout", {}):
                        config[f"test_timeout_{key}"] = items["timeout"][key]
            elif key == "machine":
                if "node_count" in items:
                    config["node_count"] = items["node_count"]
                if "cpus_per_node" in items:
                    config["cpus_per_node"] = items["cpus_per_node"]
                if "gpus_per_node" in items:
                    config["gpus_per_node"] = items["gpus_per_node"]
            elif key == "batch":
                if "length" in items:
                    config["batch_length"] = items["length"]
            elif key in ("variables", "build"):
                config[key] = items

    def set_main_options(self, args: argparse.Namespace) -> None:
        logging.set_level(logging.INFO)
        log_levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.TRACE)
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
        for path in args.config_mods:
            *components, value = path.split(":")
            match components:
                case ["config", "debug"] | ["debug"]:
                    self.debug = boolean(value)
                    if self.debug:
                        self.log_level = logging.get_level_name(log_levels[3])
                        logging.set_level(logging.DEBUG)
                case ["config", "cache_runtimes"] | ["cache_runtimes"]:
                    self.cache_runtimes = boolean(value)
                case ["config", "log_level"] | ["log_level"]:
                    self.log_level = value.upper()
                    level = logging.get_level(self.log_level)
                    logging.set_level(level)
                case ["batch", "length"]:
                    self.batch.length = time_in_seconds(value)
                case ["machine", key]:
                    if key not in ("node_count", "cpus_per_node", "gpus_per_node"):
                        msg = f"Illegal configuration setting: {path}"
                        raise ValueError(path)
                    self.update_resource_counts(**{key: int(value)})
                case ["test", key]:
                    if key not in ("timeout_fast", "timeout_long", "timeout_default"):
                        msg = f"Illegal configuration setting: {path}"
                        raise ValueError(msg)
                    setattr(self.test, key, time_in_seconds(value))
        if getattr(args, "session_node_count", None) is not None:
            self.session.node_count = args.session_node_count
        if getattr(args, "session_node_ids", None) is not None:
            self.session.node_ids = args.session_node_ids
        if getattr(args, "session_cpu_count", None) is not None:
            self.session.cpu_count = args.session_cpu_count
        if getattr(args, "session_cpu_ids", None) is not None:
            self.session.cpu_ids = args.session_cpu_ids
        if getattr(args, "session_gpu_count", None) is not None:
            self.session.gpu_count = args.session_gpu_count
        if getattr(args, "session_gpu_ids", None) is not None:
            self.session.gpu_ids = args.session_gpu_ids
        if getattr(args, "session_workers", None) is not None:
            self.session.workers = args.session_workers
        if getattr(args, "session_timeout", None) is not None:
            self.session.timeout = args.session_timeout
        if getattr(args, "test_node_count", None) is not None:
            self.test.node_count = tuple(args.test_node_count)
        if getattr(args, "test_cpu_count", None) is not None:
            self.test.cpu_count = tuple(args.test_cpu_count)
        if getattr(args, "test_gpu_count", None) is not None:
            self.test.cpu_count = tuple(args.test_gpu_count)
        if getattr(args, "test_timeout", None) is not None:
            self.test.timeout = args.test_timeout
        if getattr(args, "test_timeoutx", None) is not None:
            self.test.timeoutx = args.test_timeoutx
        if getattr(args, "batch_length", None) is not None:
            self.batch.length = args.batch_length
        if getattr(args, "batch_count", None) is not None:
            self.batch.count = args.batch_count
        if getattr(args, "batch_workers", None) is not None:
            self.batch.workers = args.batch_workers
        if getattr(args, "batch_scheduler", None) is not None:
            self.batch.scheduler = None if args.batch_scheduler == "null" else args.batch_scheduler
        if getattr(args, "batch_scheduler_args", None) is not None:
            self.batch.scheduler_args = args.batch_scheduler_args
        self.options = args

    @classmethod
    def read_config(cls, file: str) -> dict:
        try:
            import toml
        except ImportError:
            logging.warning("Install toml to read configuration file {file!r}")
            return {}

        data = toml.load(file)
        variables = dict(os.environ)

        # make variables available in other config sections
        if "variables" in data:
            section_data = data["variables"]
            for key, raw_value in section_data.items():
                value = expandvars(raw_value, variables)
                section_data[key] = str(safe_loads(value))
                variables[key] = section_data[key]

        for section in data:
            if section == "variables":
                continue
            for key, raw_value in data[section].items():
                value = expandvars(raw_value, variables)
                data[section][key] = safe_loads(value)

        config: dict[str, Any] = {}
        # expand any keys given as a:b:c
        for path, section_data in data.items():
            if path in section_schemas:
                logging.warning(f"ignoring unrecognized config section: {path}")
            schema = section_schemas[section]
            try:
                schema.validate({section: section_data})
            except SchemaError as e:
                msg = f"Schema error encountered in {file}: {e.args[0]}"
                raise ValueError(msg) from None
            config[section] = section_data
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
            return os.path.abspath("./nvtest.toml")
        return None

    @classmethod
    def save(cls, path: str, scope: str | None = None):
        import toml

        file = cls.config_file(scope or "local")
        assert file is not None
        section, key, value = path.split(":")
        with open(file, "r") as fh:
            config = toml.load(fh)
        config.setdefault(section, {})[key] = safe_loads(value)
        with open(file, "w") as fh:
            toml.dump(config, fh)

    def getoption(self, key: str, default: Any = None) -> Any:
        """Compatibility with external tools"""
        return getattr(self.options, key, default)

    def describe(self, section: str | None = None) -> str:
        def join_ilist(a: list[Any], threshold: int = 8):
            if len(a) > threshold:
                a = a[: threshold // 2] + ["..."] + a[-threshold // 2 :]
            return ", ".join(str(_) for _ in a)

        if section is not None:
            asdict = {section: dataclasses.asdict(getattr(self, section))}
        else:
            asdict = dataclasses.asdict(self)
        if "system" in asdict:
            asdict["system"]["os"] = vars(self.system.os)
        if "session" in asdict:
            asdict["session"] = self.session.asdict()
            asdict["session"]["cpu_ids"] = join_ilist(asdict["session"]["cpu_ids"])
        if "options" in asdict:
            asdict["options"] = vars(self.options)
        if "test" in asdict:
            asdict["test"]["node_count"] = join_ilist(asdict["test"]["node_count"])
            asdict["test"]["cpu_count"] = join_ilist(asdict["test"]["cpu_count"])
            asdict["test"]["gpu_count"] = join_ilist(asdict["test"]["gpu_count"])
        try:
            import yaml

            return yaml.dump(asdict, default_flow_style=False)
        except ImportError:
            return json.dumps(asdict, indent=2)


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


def expandvars(arg: str, mapping: dict) -> str:
    t = Template(arg)
    return t.safe_substitute(mapping)


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg
