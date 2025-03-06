import argparse
import dataclasses
import json
import os
from string import Template
from types import SimpleNamespace
from typing import Any
from typing import TextIO

import hpc_connect
import yaml

from ..plugins.manager import CanaryPluginManager
from ..third_party import color
from ..third_party.schema import Schema
from ..third_party.schema import SchemaError
from ..util import logging
from ..util.collections import merge
from ..util.filesystem import find_work_tree
from ..util.rprobe import cpu_count
from . import _machine
from .rpool import ResourcePool
from .schemas import batch_schema
from .schemas import build_schema
from .schemas import config_schema
from .schemas import environment_schema
from .schemas import resource_schema
from .schemas import test_schema

section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "batch": batch_schema,
    "config": config_schema,
    "environment": environment_schema,
    "resource_pool": resource_schema,
    "test": test_schema,
}

log_levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.TRACE)


class EnvironmentModifications:
    def __init__(self, arg: dict[str, dict[str, str] | list[str]] | None = None) -> None:
        self.mods: dict[str, Any] = {}
        self.update(arg or {})

    def update(self, arg: dict[str, Any]) -> None:
        for action, items in arg.items():
            if action == "set":
                self.set(**items)
            elif action == "unset":
                self.unset(*items)
            elif action in ("prepend-path", "prepend_path"):
                for pathname, path in items.items():
                    self.prepend_path(pathname, path)
            elif action in ("append-path", "append_path"):
                for pathname, path in items.items():
                    self.append_path(pathname, path)
            else:
                raise KeyError(action)

    def getstate(self) -> dict[str, Any]:
        return dict(self.mods)

    def set(self, **vars: str) -> None:
        self.mods.setdefault("set", {}).update(vars)
        for name, value in vars.items():
            os.environ[name] = value

    def unset(self, *vars: str) -> None:
        self.mods.setdefault("unset", []).extend(vars)
        for name in vars:
            os.environ.pop(name, None)

    def prepend_path(self, pathname: str, path: str) -> None:
        self.mods.setdefault("prepend-path", {}).update({pathname: path})
        if existing := os.getenv(pathname):
            os.environ[pathname] = f"{path}:{existing}"
        else:
            os.environ[pathname] = path

    def append_path(self, pathname: str, path: str, sep: str = ":") -> None:
        self.mods.setdefault("append-path", {}).update({pathname: path})
        if existing := os.getenv(pathname):
            os.environ[pathname] = f"{existing}{sep}{path}"
        else:
            os.environ[pathname] = path


class SessionConfig:
    __slots__ = ("work_tree", "stage", "level")

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
        d: dict[str, str | int | None] = {}
        d["work_tree"] = self.work_tree
        # these are set during the process
        d["stage"] = None
        d["level"] = None
        return d


@dataclasses.dataclass
class Test:
    timeout_fast: float = 120.0
    timeout_default: float = 5 * 60.0
    timeout_long: float = 15 * 60.0
    timeout_ctest: float = 1500.0

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
            if "paths" in compiler:
                compiler.update(compiler.pop("paths"))
            for key, value in compiler.items():
                setattr(self.compiler, key, value)
        for key, value in data.items():
            setattr(self, key, value)


@dataclasses.dataclass
class Batch:
    duration: float = 30 * 60  # 30 minutes
    default_options: list[str] = dataclasses.field(default_factory=list)

    def update(self, *args: Any, **kwargs: Any) -> None:
        if len(args) > 1:
            raise TypeError(f"Batch.update() expected at most 1 argument, got {len(args)}")
        data = dict(*args) | kwargs
        for key, value in data.items():
            setattr(self, key, value)


@dataclasses.dataclass
class Config:
    """Access to configuration values"""

    invocation_dir: str = os.getcwd()
    working_dir: str = os.getcwd()
    debug: bool = False
    multiprocessing_context: str = "spawn"
    log_level: str = "INFO"
    _config_dir: str | None = None
    scheduler: hpc_connect.HPCScheduler | None = None
    system: System = dataclasses.field(default_factory=System)
    session: SessionConfig = dataclasses.field(default_factory=SessionConfig)
    test: Test = dataclasses.field(default_factory=Test)
    environment: EnvironmentModifications = dataclasses.field(
        default_factory=EnvironmentModifications
    )
    batch: Batch = dataclasses.field(default_factory=Batch)
    build: Build = dataclasses.field(default_factory=Build)
    options: argparse.Namespace = dataclasses.field(default_factory=argparse.Namespace)
    resource_pool: ResourcePool = dataclasses.field(default_factory=ResourcePool)
    _plugin_manager: CanaryPluginManager | None = dataclasses.field(default=None)

    @classmethod
    def factory(cls) -> "Config":
        """Create the configuration object"""
        self = cls.create()
        root = find_work_tree()
        if root:
            # If we are inside a session directory, then we want to restore its configuration
            # any changes create happens before setting command line options, so changes can still
            # be made to the restored configuration
            file = os.path.join(root, ".canary/config")
            if os.path.exists(file):
                with open(file) as fh:
                    self.restore_from_snapshot(fh)
            else:
                raise FileNotFoundError(file)
        return self

    @classmethod
    def create(cls) -> "Config":
        user_defined_config: dict[str, Any] = {}
        cls.load_config("global", user_defined_config)
        cls.load_config("local", user_defined_config)
        kwds: dict[str, Any] = user_defined_config.pop("config", {})
        self = cls(**kwds)
        for section, items in user_defined_config.items():
            if not hasattr(self, section):
                continue
            obj = getattr(self, section)
            if hasattr(obj, "update"):
                obj.update(items)
        return self

    @property
    def config_dir(self) -> str | None:
        if self._config_dir is None:
            self._config_dir = get_config_dir()
        return self._config_dir

    @property
    def plugin_manager(self) -> CanaryPluginManager:
        if self._plugin_manager is None:
            self._plugin_manager = CanaryPluginManager.factory()
        return self._plugin_manager

    @plugin_manager.setter
    def plugin_manager(self, arg: CanaryPluginManager) -> None:
        self._plugin_manager = arg

    def restore_from_snapshot(self, fh: TextIO) -> None:
        snapshot = json.load(fh)
        self.system = System(snapshot["system"])
        self.environment = EnvironmentModifications(snapshot["environment"])
        self.session = SessionConfig(**snapshot["session"])
        self.test = Test(**snapshot["test"])
        compiler = Compiler(**snapshot["build"].pop("compiler"))
        self.build = Build(compiler=compiler, **snapshot["build"])
        self.resource_pool = ResourcePool()
        self.resource_pool.update(snapshot["resource_pool"])
        self.setup_hpc_connect(snapshot["scheduler"])
        self.update(snapshot["config"])
        self.batch = Batch(**snapshot["batch"])
        for f in snapshot["plugin_manager"]["plugins"]:
            self.plugin_manager.consider_plugin(f)

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variable CANARY_LEVEL=1 to guard against this case.
        if os.getenv("CANARY_LEVEL") == "1":
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
        logging.debug(f"Reading configuration from {file}")
        file_data = cls.read_config(file)
        for key, items in file_data.items():
            if key == "config":
                if "debug" in items:
                    config["debug"] = bool(items["debug"])
                if "_config_dir" in items:
                    config["_config_dir"] = items["_config_dir"]
                if "log_level" in items:
                    config["log_level"] = items["log_level"]
                if "multiprocessing_context" in items:
                    config["multiprocessing_context"] = items["multiprocessing_context"]
            elif key == "test":
                for name in ("fast", "long", "default"):
                    if name in items.get("timeout", {}):
                        config[f"test_timeout_{name}"] = items["timeout"][name]
            elif key == "batch":
                if "duration" in items:
                    config["batch_duration"] = items["duration"]
                elif "length" in items:
                    config["batch_duration"] = items["length"]
            elif key in section_schemas:
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
        if "_config_dir" in data:
            self._config_dir = data["_config_dir"]
        if "log_level" in data:
            self.log_level = data["log_level"].upper()
            level = logging.get_level(self.log_level)
            logging.set_level(level)
        if "multiprocessing_context" in data:
            self.multiprocessing_context = data["multiprocessing_context"]

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
            self.environment.update({"set": args.env_mods["session"]})

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variable CANARY_LEVEL=1 to guard against this case.  But, if we are
        # running tests inside an existing test session and no batch arguments are given, we want
        # to use the original batch arguments.
        batchopts = getattr(args, "batch", None) or {}
        if os.getenv("CANARY_LEVEL") == "1":
            batchopts = {}
        if cached_batchopts := getattr(self.options, "batch", None):
            batchopts = merge(cached_batchopts, batchopts)
        scheduler = batchopts.get("scheduler")
        self.setup_hpc_connect(scheduler)
        if self.scheduler is None:
            batchopts.clear()
        args.batch = batchopts

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
            if n > cpu_count():
                raise ValueError(f"workers={n} > cpu_count={cpu_count()}")

        if b := getattr(args, "batch", None):
            if n := b.get("workers"):
                if n > cpu_count():
                    raise ValueError(f"batch:workers={n} > cpu_count={cpu_count()}")

        if t := getattr(args, "test_timeout", None):
            for key, value in t.items():
                setattr(self.test, f"timeout_{key}", value)

        self.options = args

    def setup_hpc_connect(self, name: str | None) -> None:
        """Set the hpc_connect library"""
        if name in ("null", None):
            self.scheduler = None
        else:
            logging.debug(f"Setting up HPC Connect for {name}")
            assert name is not None
            self.scheduler = hpc_connect.scheduler(name)
            logging.debug(f"  HPC connect: node count: {self.scheduler.config.node_count}")
            logging.debug(f"  HPC connect: CPUs per node: {self.scheduler.config.cpus_per_node}")
            logging.debug(f"  HPC connect: GPUs per node: {self.scheduler.config.gpus_per_node}")
            self.resource_pool.fill_uniform(
                node_count=self.scheduler.config.node_count,
                cpus_per_node=self.scheduler.config.cpus_per_node,
                gpus_per_node=self.scheduler.config.gpus_per_node,
            )

    @classmethod
    def read_config(cls, file: str) -> dict:
        with open(file) as fh:
            data = yaml.safe_load(fh)

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
            return os.path.abspath("./canary.yaml")
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
            if key == "_plugin_manager":
                d["plugin_manager"] = {"plugins": list(value.considered)}
            elif dataclasses.is_dataclass(value):
                d[key] = dataclasses.asdict(value)  # type: ignore
                if key == "system":
                    d[key]["os"] = vars(d[key]["os"])
            elif hasattr(value, "getstate"):
                d[key] = value.getstate()
            elif isinstance(value, (argparse.Namespace, SimpleNamespace)):
                d[key] = vars(value)
            elif key == "scheduler":
                d[key] = getattr(value, "name", None)
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


def get_config_dir() -> str | None:
    config_dir: str
    if "CANARY_CONFIG_DIR" in os.environ:
        config_dir = os.environ["CANARY_CONFIG_DIR"]
    elif "XDG_CONFIG_HOME" in os.environ:
        config_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "canary")
    else:
        config_dir = os.path.expanduser("~/.config/canary")
    if config_dir in (os.devnull, "null"):
        return None
    return config_dir


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg
