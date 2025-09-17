import argparse
import io
import json
import os
import sys
from collections.abc import ValuesView
from contextlib import contextmanager
from copy import deepcopy
from functools import cached_property
from string import Template
from typing import IO
from typing import Any
from typing import Generator
from typing import MutableMapping

import yaml

from ..plugins.manager import CanaryPluginManager
from ..third_party import color
from ..third_party.schema import Schema
from ..util import logging
from ..util.collections import merge
from ..util.compression import compress64
from ..util.compression import expand64
from ..util.filesystem import find_work_tree
from ..util.filesystem import mkdirp
from ..util.rprobe import cpu_count
from ..util.string import strip_quotes
from . import _machine
from .rpool import ResourcePool
from .schemas import any_schema
from .schemas import batch_schema
from .schemas import build_schema
from .schemas import config_schema
from .schemas import environment_schema
from .schemas import machine_schema
from .schemas import plugin_schema
from .schemas import resource_schema
from .schemas import user_schema

invocation_dir = os.getcwd()


section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "batch": batch_schema,
    "config": config_schema,
    "environment": environment_schema,
    "resource_pool": resource_schema,
    "session": any_schema,
    "system": any_schema,
    "plugin": plugin_schema,
    "user": user_schema,
    "machine": machine_schema,
}


log_levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)
env_archive_name = "CANARYCFG64"

logger = logging.get_logger("_canary")


class ConfigScope:
    def __init__(self, name: str, file: str | None, data: dict[str, Any]) -> None:
        self.name = name
        self.file = file
        self.data = data

    def __repr__(self):
        file = self.file or "<none>"
        return f"ConfigScope({self.name}: {file})"

    def __eq__(self, other):
        if not isinstance(other, ConfigScope):
            return False
        return self.name == other.name and self.file == other.file and other.data == self.data

    def __iter__(self):
        return iter(self.data)

    def __setitem__(self, path: str, value: Any) -> None:
        parts = process_config_path(path)
        section = parts.pop(0)
        section_data = self.data.get(section, {})
        data = section_data
        while len(parts) > 1:
            key = parts.pop(0)
            new = data.get(key, {})
            if isinstance(new, dict):
                new = dict(new)
                # reattach to parent object
                data[key] = new
            data = new
        # update new value
        data[parts[0]] = value
        self.data[section] = section_data

    def get_section(self, section: str) -> Any:
        return self.data.get(section)

    def pop_section(self, section: str) -> Any:
        return self.data.pop(section, None)

    def asdict(self) -> dict[str, Any]:
        data = {"name": self.name, "file": self.file, "data": self.data.copy()}
        return data

    def dump(self, root: str | None = None) -> None:
        if self.file is None:
            return
        root = root or "canary"
        with open(self.file, "w") as fh:
            yaml.dump({root or "canary": self.data}, fh, default_flow_style=False)


class Config:
    def __init__(self) -> None:
        self.invocation_dir = invocation_dir
        self.working_dir = os.getcwd()
        self._resource_pool: ResourcePool = ResourcePool()
        self.pluginmanager: CanaryPluginManager = CanaryPluginManager.factory()
        self.options: argparse.Namespace = argparse.Namespace()
        self.scopes: dict[str, ConfigScope] = {}
        if envcfg := os.getenv(env_archive_name):
            with io.StringIO() as fh:
                fh.write(expand64(envcfg))
                fh.seek(0)
                self.load_snapshot(fh)
        elif root := find_work_tree():
            # If we are inside a session directory, then we want to restore its configuration.
            file = os.path.join(root, ".canary/config")
            if os.path.exists(file):
                with open(file) as fh:
                    self.load_snapshot(fh)
            else:
                raise FileNotFoundError(file)
        else:
            self.scopes["defaults"] = ConfigScope("defaults", None, default_config_values())
            for scope in ("global", "local"):
                config_scope = read_config_scope(scope)
                self.push_scope(config_scope)
            if cscope := read_env_config():
                self.push_scope(cscope)
        if self.get("config:debug"):
            logging.set_level(logging.DEBUG)

    def getoption(self, name: str, default: Any = None) -> Any:
        value = getattr(self.options, name, None)
        if value is None:
            return default
        return value

    def getstate(self, pretty: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {}
        sections = set([sec for scope in self.scopes.values() for sec in scope.data])
        for section in sections:
            section_data = self.get_config(section)
            data[section] = section_data
        data["resource_pool"] = self._resource_pool.getstate()
        data["options"] = vars(self.options)
        data["invocation_dir"] = self.invocation_dir
        data["working_dir"] = self.working_dir
        return data

    @cached_property
    def cache_dir(self) -> str | None:
        """Get the directory for cache files.

        Lazily initializes the cache directory path, creating it if necessary.

        Returns:
            The path to the cache directory or None if not set.
        """
        cache_dir: str
        if dir := self.get("config:cache_dir"):
            cache_dir = os.path.expanduser(dir)
        else:
            cache_dir = os.path.join(self.invocation_dir, ".canary_cache")
        if isnullpath(cache_dir):
            return None
        create_cache_dir(cache_dir)
        return cache_dir

    @property
    def resource_pool(self) -> ResourcePool:
        if self._resource_pool.empty():
            self._resource_pool.fill_default()
        return self._resource_pool

    def read_only_scope(self, scope: str) -> bool:
        return scope in ("defaults", "environment", "command_line")

    def push_scope(self, scope: ConfigScope) -> None:
        if pool := scope.pop_section("resource_pool"):
            self._resource_pool.clear()
            self._resource_pool.update(pool)
        if envmods := scope.get_section("environment"):
            self.apply_environment_mods(envmods)
        self.scopes[scope.name] = scope
        if cfg := scope.get_section("config"):
            if plugins := cfg.get("plugins"):
                for f in plugins:
                    self.pluginmanager.consider_plugin(f)

    def pop_scope(self, scope: ConfigScope) -> ConfigScope | None:
        return self.scopes.pop(scope.name, None)

    def get_config(self, section: str, scope: str | None = None) -> Any:
        scopes: ValuesView[ConfigScope] | list[ConfigScope]
        if scope is None:
            scopes = self.scopes.values()
        else:
            scopes = [self.validate_scope(scope)]
        merged_section: dict[str, Any] = {}
        for config_scope in scopes:
            assert isinstance(config_scope, ConfigScope), str(config_scope)
            data = config_scope.get_section(section)
            if not data or not isinstance(data, dict):
                continue
            merged_section = merge(merged_section, {section: data})
        if section not in merged_section:
            return {}
        return merged_section[section]

    def get(self, path: str, default: Any = None, scope: str | None = None) -> Any:
        parts = process_config_path(path)
        section = parts.pop(0)
        value = self.get_config(section, scope=scope)
        while parts:
            key = parts.pop(0)
            # cannot use value.get(key, default) in case there is another part
            # and default is not a dict
            if key not in value:
                return default
            value = value[key]
        return value

    def set(self, path: str, value: Any, scope: str | None = None) -> None:
        if ":" not in path:
            # handle bare section name as path
            self.update_config(path, value, scope=scope)
            return
        parts = process_config_path(path)
        section = parts.pop(0)
        section_data = self.get_config(section, scope=scope)
        data = section_data
        while len(parts) > 1:
            key = parts.pop(0)
            new = data.get(key, {})
            if isinstance(new, dict):
                new = dict(new)
                # reattach to parent object
                data[key] = new
            data = new
        # update new value
        data[parts[0]] = value
        self.update_config(section, section_data, scope=scope)
        if section == "environment":
            self.apply_environment_mods(section_data)

    def add(self, fullpath: str, scope: str | None = None) -> None:
        path: str = ""
        existing: Any = None
        components = process_config_path(fullpath)
        has_existing_value = True
        for idx, name in enumerate(components[:-1]):
            path = name if not path else f"{path}:{name}"
            existing = self.get(path, scope=scope)
            if existing is None:
                has_existing_value = False
                # construct value from this point down
                value = try_loads(components[-1])
                for component in reversed(components[idx + 1 : -1]):
                    value = {component: value}
                break

        if has_existing_value:
            path = ":".join(components[:-1])
            value = try_loads(strip_quotes(components[-1]))
            existing = self.get(path, scope=scope)

        if isinstance(existing, list) and not isinstance(value, list):
            # append values to lists
            value = [value]

        new = merge(existing, value)
        self.set(path, new, scope=scope)

    def create_scope(self, name: str, file: str | None, data: dict[str, Any]) -> ConfigScope:
        for value in self.scopes.values():
            if value.name == name:
                if value.file != file:
                    raise ValueError(
                        f"The config scope {name!r} already exists at file={value.file}"
                    )
                value.data = merge(value.data, data)
                return value
        scope = ConfigScope(name, file, data)
        self.push_scope(scope)
        return scope

    def highest_precedence_scope(self) -> ConfigScope:
        """Non-internal scope with highest precedence."""
        file_scopes = [scope for scope in self.scopes.values() if scope.file is not None]
        return next(reversed(file_scopes))

    def validate_scope(self, scope: str | None) -> ConfigScope:
        if scope is None:
            return self.highest_precedence_scope()
        elif scope in self.scopes:
            return self.scopes[scope]
        elif scope == "internal":
            cfgscope = ConfigScope("internal", None, {})
            self.push_scope(cfgscope)
            return cfgscope
        else:
            raise ValueError(f"Invalid scope {scope!r}")

    def update_config(self, section: str, update_data: dict[str, Any], scope: str | None = None):
        """Update the configuration file for a particular scope.

        Args:
            section (str): section of the configuration to be updated
            update_data (dict): data to be used for the update
            scope (str): scope to be updated
        """
        if scope is None:
            config_scope = self.highest_precedence_scope()
        else:
            config_scope = self.scopes[scope]
        # read only the requested section's data.
        config_scope.data[section] = dict(update_data)
        config_scope.dump(root="canary")

    def set_main_options(self, args: argparse.Namespace) -> None:
        """Set main configuration options based on command-line arguments.

        Updates the configuration attributes based on the provided argparse Namespace containing
        command-line arguments.

        Args:
            args: An argparse.Namespace object containing command-line arguments.
        """
        data: dict[str, Any] = {}

        if cache_dir := getattr(args, "cache_dir", None):
            data.setdefault("config", {})["cache_dir"] = cache_dir

        logging.set_level(logging.INFO)
        if args.color is not None:
            color.set_color_when(args.color)

        if args.q or args.v:
            i = min(max(2 - args.q + args.v, 0), 4)
            data.setdefault("config", {})["log_level"] = logging.get_level_name(log_levels[i])
            logging.set_level(log_levels[i])

        if args.debug:
            data.setdefault("config", {})["debug"] = True
            data.setdefault("config", {})["log_level"] = logging.get_level_name(log_levels[3])
            logging.set_level(logging.DEBUG)

        errors: int = 0
        if args.config_mods:
            data.update(deepcopy(args.config_mods))

        # handle resource pool separately
        resource_pool_mods: dict[str, Any] = {}
        if "resource_pool" in data:
            resource_pool_mods.update(data.pop("resource_pool"))

        for section, section_data in data.items():
            if section not in section_schemas:
                errors += 1
                logger.error(f"Illegal config section: {section!r}")
                continue
            schema = section_schemas[section]
            data[section] = schema.validate({section: section_data})[section]

        if resource_pool_mods:
            if self._resource_pool.empty():
                schema = section_schemas["resource_pool"]
                pool = schema.validate({"resource_pool": resource_pool_mods})["resource_pool"]
                self._resource_pool.update(pool)
            else:
                self._resource_pool.add(**resource_pool_mods)

        if errors:
            raise ValueError("Stopping due to previous errors")

        if n := getattr(args, "workers", None):
            if n > cpu_count():
                raise ValueError(f"workers={n} > cpu_count={cpu_count()}")

        if t := getattr(args, "timeouts", None):
            c = data.setdefault("config", {})
            c.setdefault("timeout", {}).update(t)

        self.options = merge_namespaces(self.options, args)

        scope = ConfigScope("command_line", None, data)
        self.push_scope(scope)

        if self.get("config:debug", scope="command_line"):
            logging.set_level(logging.DEBUG)

    def load_snapshot(self, file: IO[Any]) -> None:
        snapshot = json.load(file)
        if "config" in snapshot:
            snapshot = convert_legacy_snapshot(snapshot)
        properties: dict[str, Any] = snapshot["properties"]
        self.working_dir = properties["working_dir"]
        self.invocation_dir = properties["invocation_dir"]
        if pool := properties.pop("resource_pool", None):
            self._resource_pool.clear()
            self._resource_pool.update(pool)
        if options := properties.pop("options", None):
            self.options = argparse.Namespace(**options)
        self.scopes.clear()
        for value in snapshot["scopes"]:
            scope = ConfigScope(value["name"], value["file"], value["data"])
            self.push_scope(scope)

        if not len(logger.handlers):
            logging.setup_logging()
        log_level = self.get("config:log_level")
        if logging.get_level_name(logger.level) != log_level:
            logging.set_level(log_level)
        if root := find_work_tree():
            f = os.path.abspath(os.path.join(root, ".canary/log.txt"))
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler) and handler.baseFilename == f:
                    break
            else:
                logging.add_file_handler(f, logging.DEBUG)

    def dump_snapshot(self, file: IO[Any], indent: int | None = None) -> None:
        snapshot: dict[str, Any] = {}
        properties = snapshot.setdefault("properties", {})
        properties["resource_pool"] = self._resource_pool.getstate()
        properties["options"] = vars(self.options)
        properties["invocation_dir"] = self.invocation_dir
        properties["working_dir"] = self.working_dir
        scopes = snapshot.setdefault("scopes", [])
        for scope in self.scopes.values():
            scopes.append(scope.asdict())
        file.write(json.dumps(snapshot, indent=indent))

    def archive(self, mapping: MutableMapping) -> None:
        file = io.StringIO()
        self.dump_snapshot(file)
        mapping[env_archive_name] = compress64(file.getvalue())

    def apply_environment_mods(self, envmods: dict[str, Any]) -> None:
        for action, values in envmods.items():
            if action == "set":
                for name, value in values.items():
                    os.environ[name] = value
            elif action == "unset":
                for value in values:
                    os.environ.pop(value, None)
            elif action == "prepend-path":
                for pathname, path in values.items():
                    if existing := os.getenv(pathname):
                        os.environ[pathname] = f"{path}:{existing}"
                    else:
                        os.environ[pathname] = path
            elif action == "append-path":
                for pathname, path in values.items():
                    if existing := os.getenv(pathname):
                        os.environ[pathname] = f"{existing}:{path}"
                    else:
                        os.environ[pathname] = path

    @contextmanager
    def temporary_scope(self) -> Generator[ConfigScope, None, None]:
        scope = ConfigScope("tmp", None, {})
        self.push_scope(scope)
        try:
            yield scope
        finally:
            self.pop_scope(scope)


def read_config_scope(scope: str) -> ConfigScope:
    data: dict[str, Any] = {}
    if file := get_scope_filename(scope):
        if fd := read_config_file(file):
            if "canary" in fd:
                data.update(fd.pop("canary"))
            data.update(fd)
        for section, section_data in data.items():
            if schema := section_schemas.get(section):
                if schema == any_schema:
                    data[section] = section_data
                else:
                    data[section] = schema.validate({section: section_data})[section]
            else:
                logger.warning(f"ignoring unrecognized config section: {section}")
    return ConfigScope(scope, file, data)


def read_config_file(file: str) -> dict[str, Any] | None:
    """Load configuration settings from ``file``"""
    if not os.path.exists(file):
        return None
    with open(file) as fh:
        return yaml.safe_load(fh)


def get_scope_filename(scope: str) -> str | None:
    if scope == "site":
        if var := os.getenv("CANARY_SITE_CONFIG"):
            return var
        return os.path.join(sys.prefix, "etc/canary/config.yaml")
    elif scope == "global":
        if var := os.getenv("CANARY_GLOBAL_CONFIG"):
            return var
        elif var := os.getenv("XDG_CONFIG_HOME"):
            file = os.path.join(var, "canary/config.yaml")
            if os.path.exists(file):
                return file
        return os.path.expanduser("~/.config/canary.yaml")
    elif scope == "local":
        return os.path.abspath("./canary.yaml")
    raise ValueError(f"Could not determine filename for scope {scope!r}")


def read_env_config() -> ConfigScope | None:
    data: dict[str, Any] = {}
    config_defaults = default_config_values()
    for config_var in config_defaults["config"]:
        var = f"CANARY_{config_var.upper()}"
        if var in os.environ:
            value: Any
            if var == "CANARY_PLUGINS":
                value = [_.strip() for _ in os.environ[var].split(",") if _.split()]
            else:
                value = try_loads(os.environ[var])
            data.setdefault("config", {})[config_var] = value
    if not data:
        return None
    schema = section_schemas["config"]
    data = schema.validate(data)
    return ConfigScope("environment", None, data)


def process_config_path(path: str) -> list[str]:
    result: list[str] = []
    if path.startswith(":"):
        raise ValueError(f"Illegal leading ':' in path {path}")
    while path:
        front, _, path = path.partition(":")
        result.append(front)
        if path.startswith(("{", "[")):
            result.append(path)
            return result
    return result


def try_loads(arg):
    """Attempt to deserialize ``arg`` into a python object. If the deserialization fails,
    return ``arg`` unmodified.

    """
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


def default_config_values() -> dict[str, Any]:
    defaults = {
        "config": {
            "debug": False,
            "log_level": "INFO",
            "cache_dir": os.path.join(os.getcwd(), ".canary_cache"),
            "multiprocessing": {
                "context": "spawn",
                "max_tasks_per_child": 1,
            },
            "timeout": {
                "session": -1.0,
                "multiplier": 1.0,
                "fast": 120.0,
                "default": 300.0,
                "long": 900.0,
            },
            "plugins": [],
            "polling_frequency": {
                "testcase": 0.05,
            },
        },
        "environment": {
            "prepend-path": {},
            "append-path": {},
            "set": {},
            "unset": [],
        },
        "session": {
            "work_tree": None,
            "level": None,
            "mode": None,
        },
        "system": _machine.system_config(),
        "machine": _machine.machine_config(),
        "batch": {"default_options": []},
    }
    return defaults


def isnullpath(path: str) -> bool:
    return path in ("null", os.devnull)


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


def convert_legacy_snapshot(legacy: dict[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    properties = snapshot.setdefault("properties", {})
    properties["resource_pool"] = legacy["resource_pool"]
    properties["options"] = legacy["options"]
    properties["invocation_dir"] = legacy["config"].pop("invocation_dir")
    properties["working_dir"] = legacy["config"].pop("working_dir")

    scope: dict[str, Any] = {"name": "defaults", "file": None}
    data = scope.setdefault("data", {})
    data["build"] = legacy["build"]
    data["environment"] = legacy["environment"]
    data["session"] = legacy["session"]
    data["system"] = legacy["system"]
    data["config"] = legacy["config"]
    data["config"]["cache_dir"] = os.path.join(properties["invocation_dir"], ".canary_cache")
    if "mulitprocessing_context" in data["config"]:
        data["config"]["multiprocessing"] = {
            "context": data["config"].pop("multiprocessing_context", "spawn"),
            "max_tasks_per_child": 1,
        }
    data["config"]["plugins"] = legacy["pluginmanager"]["plugins"]
    if "test" in legacy:
        data["config"]["timeout"] = legacy["test"]["timeout"]
    data["config"].pop("_config_dir", None)
    snapshot.setdefault("scopes", []).append(scope)
    return snapshot
