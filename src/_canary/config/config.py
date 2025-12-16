# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import sys
from functools import cached_property
from pathlib import Path
from string import Template
from typing import IO
from typing import Any
from typing import Literal
from typing import cast

import yaml

from ..pluginmanager import CanaryPluginManager
from ..util import json_helper as json
from ..util import logging
from ..util.collections import merge
from ..util.filesystem import write_directory_tag
from ..util.rich import set_color_when
from ._machine import system_config
from .schemas import config_schema
from .schemas import environment_variable_schema

invocation_dir = os.getcwd()


log_levels: tuple[int, ...] = (
    logging.TRACE,
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)

TOP_LEVEL_CONFIG_KEY = "canary"
CONFIG_ENV_FILENAME = "CANARYCFGFILE"
ConfigScopes = Literal["site", "global", "local"]

logger = logging.get_logger(__name__)


def default_config_values() -> dict[str, Any]:
    defaults = {
        "debug": False,
        "view": "TestResults",
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
        "environment": {
            "prepend-path": {},
            "append-path": {},
            "set": {},
            "unset": [],
        },
        "scratch": {},
        "system": system_config(),
    }
    return defaults


class Config:
    def __init__(self, initialize: bool = True) -> None:
        self.invocation_dir = invocation_dir
        self.pluginmanager: CanaryPluginManager = CanaryPluginManager.factory()
        self.pluginmanager.hook.canary_addhooks(pluginmanager=self.pluginmanager)
        self.data: dict[str, Any] = {}
        self.options: argparse.Namespace = argparse.Namespace()
        if initialize:
            self.init()

    def init(self) -> None:
        self.data = default_config_values()
        for name in ("site", "global", "local"):
            try:
                scope = get_config_scope_data(cast(ConfigScopes, name))
            except LocalScopeDoesNotExistError:
                continue
            self.data = merge(self.data, scope)  # type: ignore
        if env_scope := get_env_scope():
            self.data = merge(self.data, env_scope)  # type: ignore
        if self.get("debug"):
            logging.set_level(logging.DEBUG)

    @staticmethod
    def factory() -> "Config":
        config: Config = Config(initialize=False)
        if f := os.getenv(CONFIG_ENV_FILENAME):
            with open(f, "r") as fh:
                snapshot = json.load(fh)
            config.invocation_dir = snapshot["invocation_dir"]
            config.options = argparse.Namespace(**snapshot["options"])
            config.data = snapshot["data"]
            if not len(logger.handlers):
                logging.setup_logging()
            log_level = config.get("log_level")
            if logging.get_level_name(logger.level) != log_level:
                logging.set_level(log_level)
        else:
            config.init()
        for plugin in config.data["plugins"]:
            config.pluginmanager.consider_plugin(plugin)
        return config

    def dump(self, file: IO[Any]) -> None:
        snapshot: dict[str, Any] = {
            "invocation_dir": str(self.invocation_dir),
            "options": vars(self.options),
            "data": self.data,
        }
        file.write(json.dumps(snapshot, indent=2))

    def getoption(self, name: str, default: Any = None) -> Any:
        value = getattr(self.options, name, None)
        return value or default

    @cached_property
    def cache_dir(self) -> str | None:
        """Get the directory for cache files.

        Lazily initializes the cache directory path, creating it if necessary.

        Returns:
            The path to the cache directory or None if not set.
        """
        cache_dir: str
        if dir := self.get("cache_dir"):
            cache_dir = os.path.expanduser(dir)
        else:
            cache_dir = os.path.join(self.invocation_dir, ".canary_cache")
        if isnullpath(cache_dir):
            return None
        create_cache_dir(cache_dir)
        return cache_dir

    def get(self, path: str, default: Any = None) -> Any:
        parts = process_config_path(path)
        if parts[0] == "config":
            # Legacy support for top level config key
            parts = parts[1:]
        value = self.data.get(parts[0], {})
        for key in parts[1:]:
            # cannot use value.get(key, default) in case there is another part
            # and default is not a dict
            if key not in value:
                return default
            value = value[key]
        return value

    def set(self, path: str, value: Any) -> None:
        parts = process_config_path(path)
        data = value
        for key in reversed(parts):
            data = {key: data}
        data = config_schema.validate(data)
        if parts[0] == "environment":
            self.apply_environment_mods(data["environment"])
        self.data = merge(self.data, data)

    def write_new(self, path: str, value: Any, scope: ConfigScopes) -> None:
        parts = process_config_path(path)
        data = value
        for key in reversed(parts):
            data = {key: data}
        data = config_schema.validate(data)
        file = get_scope_filename(scope)
        if fd := read_config_file(file):
            data = merge(fd, data)
        with open(file, "w") as fh:
            yaml.dump({TOP_LEVEL_CONFIG_KEY: data}, fh, default_flow_style=False)

    def set_main_options(self, args: argparse.Namespace) -> None:
        """Set main configuration options based on command-line arguments.

        Updates the configuration attributes based on the provided argparse Namespace containing
        command-line arguments.

        Args:
            args: An argparse.Namespace object containing command-line arguments.
        """
        data: dict[str, Any] = {}

        if args.config_file:
            if fd := read_config_file(args.config_file):
                data = config_schema.validate(fd)

        if cache_dir := getattr(args, "cache_dir", None):
            data["cache_dir"] = cache_dir

        logging.set_level(logging.INFO)
        if args.color is not None:
            set_color_when(args.color)

        if args.q or args.v:
            level_index: int = log_levels.index(logging.INFO)
            if args.q:
                level_index = min(len(log_levels), level_index + args.q)
            if args.v:
                level_index = max(0, level_index - args.v)
            levelno = log_levels[level_index]
            data["log_level"] = logging.get_level_name(levelno)
            logging.set_level(levelno)

        if args.debug:
            data["debug"] = True
            data["log_level"] = "DEBUG"
            logging.set_level(logging.DEBUG)

        if args.config_mods:
            data.update(args.config_mods)
            if envmods := args.config_mods.get("environment"):
                self.apply_environment_mods(envmods)

        # Put timeouts passed on the command line into the regular configuration
        if t := getattr(args, "timeout", None):
            timeouts: dict[str, float] = data.setdefault("timeout", {})
            for key, val in t.items():
                timeouts[key] = float(val)

        self.data = merge(self.data, data)
        self.options = args

        if self.data["debug"]:
            logging.set_level(logging.DEBUG)

    def apply_environment_mods(self, envmods: dict[str, Any]) -> None:
        """Apply modifications to the environment

        Warning:
          This modifies os.environ for the entire process
        """
        for action, values in envmods.items():
            if action == "set":
                os.environ.update(values)
            elif action == "unset":
                for value in values:
                    os.environ.pop(value, None)
            elif action == "prepend-path":
                for pathname, path in values.items():
                    existing = os.getenv(pathname, "")
                    os.environ[pathname] = f"{path}:{existing}" if existing else path
            elif action == "append-path":
                for pathname, path in values.items():
                    existing = os.getenv(pathname, "")
                    os.environ[pathname] = f"{existing}:{path}" if existing else path

    def create_scope(self, name: str, file: str | None, data: dict[str, Any]) -> None:
        # Deprecated method still used by some applications
        data = config_schema.validate(data)
        self.data = merge(self.data, data)


def get_config_scope_data(scope: ConfigScopes) -> dict[str, Any]:
    """Read the data from config scope ``data``

    By the time the data leaves, it is validated and does not contain a top-level ``canary`` field

    """
    data: dict[str, Any] = {}
    file = get_scope_filename(scope)
    if file is not None and (fd := read_config_file(file)):
        data.update(fd)
    return config_schema.validate(data)


def read_config_file(file: str | Path) -> dict[str, Any] | None:
    """Load configuration settings from ``file``"""
    file = Path(file)
    if not file.exists():
        return None
    with open(file) as fh:
        fd = yaml.safe_load(fh)
        return fd[TOP_LEVEL_CONFIG_KEY] if TOP_LEVEL_CONFIG_KEY in fd else fd


def get_scope_filename(scope: str) -> Path:
    from ..workspace import Workspace

    if scope == "site":
        if var := os.getenv("CANARY_SITE_CONFIG"):
            return Path(var)
        return Path(sys.prefix) / "etc/canary/config.yaml"
    elif scope == "global":
        if var := os.getenv("CANARY_GLOBAL_CONFIG"):
            return Path(var)
        elif var := os.getenv("XDG_CONFIG_HOME"):
            file = Path(var) / "canary/config.yaml"
            if file.exists():
                return file
        return Path("~/.config/canary.yaml").expanduser()
    elif scope == "local":
        if path := Workspace.find_workspace():
            return path / "config.yaml"
        raise LocalScopeDoesNotExistError(
            f"not a Canary workspace (or any of its parent directories): {Path.cwd()}"
        )
    raise ValueError(f"Could not determine filename for scope {scope!r}")


def get_env_scope() -> dict[str, Any]:
    variables = {key: var for key, var in os.environ.items() if key.startswith("CANARY_")}
    if variables:
        variables = environment_variable_schema.validate(variables)
    return variables


def process_config_path(path: str) -> list[str]:
    result: list[str] = []
    if path.startswith(":"):
        raise ValueError(f"Illegal leading ':' in path {path}")
    while path:
        front, _, path = path.partition(":")
        result.append(front)
        if path.startswith(("{", "[")):
            result.append(json.try_loads(path))
            return result
    return result


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
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    write_directory_tag(p / "CANARY_CACHE.TAG")


class LocalScopeDoesNotExistError(Exception):
    pass
