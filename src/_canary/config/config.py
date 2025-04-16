# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import dataclasses
import io
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
from ..util.compression import expand64
from ..util.filesystem import find_work_tree
from ..util.filesystem import mkdirp
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
    _cache_dir: str | None = None
    backend: hpc_connect.HPCBackend | None = None
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
        if cfg := os.getenv("CANARYCFG64"):
            with io.StringIO() as fh:
                fh.write(expand64(cfg))
                fh.seek(0)
                self.restore_from_snapshot(fh)
            wt = find_work_tree()
            if not os.path.samefile(wt, self.session.work_tree):  # type: ignore
                raise RuntimeError("Inconsistent configuration state detected")
        elif root := find_work_tree():
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
        cls.load_config("environ", user_defined_config)
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
    def cache_dir(self) -> str | None:
        if self._cache_dir is None:
            if d := self.getoption("cache_dir"):
                self._cache_dir = os.path.expanduser(d)
            elif d := os.getenv("CANARY_CACHE_DIR"):
                self._cache_dir = os.path.expanduser(d)
            else:
                self._cache_dir = os.path.join(self.invocation_dir, ".canary_cache")
        if isnullpath(self._cache_dir):
            return None
        create_cache_dir(self._cache_dir)
        return self._cache_dir

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
        self.update(snapshot["config"])
        self.batch = Batch(**snapshot["batch"])

        # We need to be careful when restoring the batch configuration.  If this session is being
        # restored while running a batch, restoring the batch can lead to infinite recursion.  The
        # batch runner sets the variable CANARY_LEVEL=1 to guard against this case.
        backend: str | None = None
        if os.getenv("CANARY_LEVEL") == "1":
            backend = "null"
        elif "CANARY_HPCC_BACKEND" in os.environ:
            backend = os.environ["CANARY_HPCC_BACKEND"]
        elif snapshot.get("scheduler") or snapshot.get("backend"):
            backend = snapshot.get("scheduler") or snapshot.get("backend")
        try:
            self.setup_hpc_connect(backend)
        except Exception as e:
            # Since we are restoring from a snapshot, our backend was properly set up on creation
            # but is now erroring on restoration.  This can happen, for example, if using the Flux
            # backend to run tests (Flux requires being run in a Flux session) and now the user is
            # running `canary status` outside of a Flux session.  We ignore the error.  If the
            # backend is really needed (it will only be needed by `canary run`), an error will
            # be thrown later if/when it is used.
            logging.warning(f"Failed to setup hpc_connect for {backend=}", ex=e)
        if self.backend is None:
            snapshot["options"].pop("batch", None)
        self.options = argparse.Namespace(**snapshot["options"])

        if plugins := getattr(self.options, "plugins", None):
            for f in plugins:
                self.plugin_manager.consider_plugin(f)

        return

    def snapshot(self, fh: TextIO, pretty_print: bool = True) -> None:
        snapshot = self.getstate()
        json.dump(snapshot, fh, indent=2 if pretty_print else None)

    @classmethod
    def load_config(cls, scope: str, config: dict[str, Any]) -> None:
        data: dict
        if scope == "environ":
            data = cls.read_config_from_env()
        else:
            file = cls.config_file(scope)
            if file is None or not os.path.exists(file):
                return
            logging.debug(f"Reading configuration from {file}")
            data = cls.read_config(file)
        for key, items in data.items():
            if key == "config":
                if "debug" in items:
                    config["debug"] = bool(items["debug"])
                if "log_level" in items:
                    config["log_level"] = items["log_level"]
                if "multiprocessing_context" in items:
                    config["multiprocessing_context"] = items["multiprocessing_context"]
                if "cache_dir" in items:
                    config["_cache_dir"] = os.path.expanduser(items["cache_dir"])
            elif key == "test":
                if user_defined_timeouts := items.get("timeout"):
                    for type, value in user_defined_timeouts.items():
                        config.setdefault("test", {})[f"timeout_{type}"] = value
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
            self.debug = boolean(data.pop("debug"))
            if self.debug:
                self.log_level = logging.get_level_name(log_levels[3])
                logging.set_level(logging.DEBUG)
        if "log_level" in data:
            self.log_level = data.pop("log_level").upper()
            level = logging.get_level(self.log_level)
            logging.set_level(level)
        if "warnings" in data:
            logging.set_warning_level(data.pop("warnings"))
        for key, val in data.items():
            setattr(self, key, val)

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

        if args.warnings:
            logging.set_warning_level(args.warnings)

        env_mods = getattr(args, "env_mods") or {}
        if "session" in env_mods:
            self.environment.update({"set": env_mods["session"]})

        batchopts: dict = getattr(args, "batch", None) or {}
        if backend := batchopts.get("scheduler"):
            self.setup_hpc_connect(backend)
        if self.backend is None:
            self.options.batch = {}
            batchopts.clear()
        elif cached_batchopts := getattr(self.options, "batch", None):
            batchopts = merge(batchopts, cached_batchopts)
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
            for type, value in t.items():
                setattr(self.test, f"timeout_{type}", value)

        self.options = merge_namespaces(self.options, args)

    def null(self) -> None:
        """Null opt to generate lazy config"""
        ...

    def setup_hpc_connect(self, name: str | None) -> None:
        """Set the hpc_connect library"""
        if name in ("null", "local", None):
            self.backend = None
            return
        assert name is not None
        logging.debug(f"Setting up HPC Connect for {name}")
        self.backend = hpc_connect.get_backend(name)
        if self.debug:
            hpc_connect.set_debug(True)
        logging.debug(f"  HPC connect: node count: {self.backend.config.node_count}")
        logging.debug(f"  HPC connect: CPUs per node: {self.backend.config.cpus_per_node}")
        logging.debug(f"  HPC connect: GPUs per node: {self.backend.config.gpus_per_node}")
        self.resource_pool.fill_uniform(
            node_count=self.backend.config.node_count,
            cpus_per_node=self.backend.config.cpus_per_node,
            gpus_per_node=self.backend.config.gpus_per_node,
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

    @classmethod
    def read_config_from_env(cls) -> dict:
        config: dict[str, Any] = {}
        for key, value in os.environ.items():
            if key == "CANARY_DEBUG":
                section = config.setdefault("config", {})
                section["debug"] = boolean(value)
            elif key == "CANARY_LOG_LEVEL":
                section = config.setdefault("config", {})
                section["log_level"] = value
            elif key == "CANARY_CACHE_DIR":
                section = config.setdefault("config", {})
                section["cache_dir"] = value
            elif key == "CANARY_MULTIPROCESSING_CONTEXT":
                section = config.setdefault("config", {})
                section["multiprocessing_context"] = value
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

    def save(self, path: str, scope: str | None = None):
        file = self.config_file(scope or "local")
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

    def getstate(self, pretty: bool = False) -> dict[str, Any]:
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
            elif key == "backend":
                d[key] = getattr(value, "name", None)
            else:
                if pretty and key.startswith("_"):
                    # print value given by getter
                    key = key[1:]
                    if hasattr(self, key):
                        value = getattr(self, key)
                d.setdefault("config", {})[key] = value
        return d

    def describe(self, section: str | None = None) -> str:
        state = self.getstate(pretty=True)
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
    if isnullpath(config_dir):
        return None
    return config_dir


def create_cache_dir(path: str) -> None:
    if isnullpath(path):
        return
    path = os.path.expanduser(path)
    file = os.path.join(path, "CACHEDIR.TAG")
    if not os.path.exists(file):
        mkdirp(path)
        with open(file, "w") as fh:
            fh.write("Signature: 8a477f597d28d172789f06886806bc55\n")
            fh.write("# This file is a cache directory tag automatically created by canary.\n")
            fh.write("# For information about cache directory tags ")
            fh.write("see https://bford.info/cachedir/\n")


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


def merge_namespaces(dest: argparse.Namespace, source: argparse.Namespace) -> argparse.Namespace:
    for attr, value in vars(source).items():
        if value is None:
            continue
        elif not hasattr(dest, attr):
            setattr(dest, attr, value)
        else:
            my_value = getattr(dest, attr)
            if hasattr(my_value, "copy"):
                my_value = my_value.copy()
            setattr(dest, attr, merge(my_value, value))
    return dest


def isnullpath(path: str) -> bool:
    return path in ("null", os.devnull)
