import argparse
import json
import json.decoder
import os
import sys
from functools import cached_property
from string import Template
from typing import IO
from typing import Any

import yaml
from schema import Schema

from ..plugins.manager import CanaryPluginManager
from ..third_party import color
from ..util import logging
from ..util.collections import merge
from ..util.filesystem import write_directory_tag
from . import _machine
from .schemas import any_schema
from .schemas import build_schema
from .schemas import config_schema
from .schemas import environment_schema
from .schemas import environment_variable_schema
from .schemas import plugin_schema

invocation_dir = os.getcwd()


section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "config": config_schema,
    "environment": environment_schema,
    "plugin": plugin_schema,
    "system": any_schema,
    "scratch": any_schema,
    "options": any_schema,
}


log_levels: tuple[int, ...] = (
    logging.TRACE,
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR,
    logging.CRITICAL,
)
CONFIG_ENV_FILENAME = "CANARYCFGFILE"

logger = logging.get_logger(__name__)


def default_config_values() -> dict[str, Any]:
    defaults = {
        "config": {
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
        },
        "options": {},
        "environment": {
            "prepend-path": {},
            "append-path": {},
            "set": {},
            "unset": [],
        },
        "system": _machine.system_config(),
        "scratch": {},
    }
    return defaults


class Config:
    def __init__(self, initialize: bool = True) -> None:
        self.invocation_dir = invocation_dir
        self.working_dir = os.getcwd()
        self.pluginmanager: CanaryPluginManager = CanaryPluginManager.factory()
        self.data: dict[str, Any] = {}
        self.options: argparse.Namespace = argparse.Namespace()
        if initialize:
            self.init()

    def init(self) -> None:
        self.data = default_config_values()
        for name in ("site", "global", "local"):
            scope = get_config_scope(name)
            self.data = merge(self.data, scope)
        if ws_scope := get_workspace_config():
            self.data = merge(self.data, ws_scope)
        if env_scope := get_env_scope():
            self.data = merge(self.data, env_scope)
        if self.get("config:debug"):
            logging.set_level(logging.DEBUG)

    @staticmethod
    def factory() -> "Config":
        config: Config = Config(initialize=False)
        if f := os.getenv(CONFIG_ENV_FILENAME):
            with open(f, "r") as fh:
                snapshot = json.load(fh)
            config.working_dir = snapshot["working_dir"]
            config.invocation_dir = snapshot["invocation_dir"]
            config.options = argparse.Namespace(**snapshot["options"])
            config.data = snapshot["data"]
            if not len(logger.handlers):
                logging.setup_logging()
            log_level = config.get("config:log_level")
            if logging.get_level_name(logger.level) != log_level:
                logging.set_level(log_level)
        else:
            config.init()
        return config

    def dump(self, file: IO[Any]) -> None:
        snapshot: dict[str, Any] = {
            "invocation_dir": str(self.invocation_dir),
            "working_dir": str(self.working_dir),
            "options": vars(self.options),
            "data": self.data,
        }
        file.write(json.dumps(snapshot, indent=2))

    def getoption(self, name: str, default: Any = None) -> Any:
        return getattr(self.options, name, default)

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

    def get(self, path: str, default: Any = None) -> Any:
        parts = process_config_path(path)
        section = parts.pop(0)
        value = self.data.get(section, {})
        while parts:
            key = parts.pop(0)
            # cannot use value.get(key, default) in case there is another part
            # and default is not a dict
            if key not in value:
                return default
            value = value[key]
        return value

    def set(self, path: str, value: Any, scope: str | None = None) -> None:
        parts = process_config_path(path)
        data = value
        for key in reversed(parts):
            data = {key: data}
        data = validate_scope(data)
        if parts[0] == "environment":
            self.apply_environment_mods(data["environment"])
        self.data = merge(self.data, data)

    def write_new(self, path: str, value: Any, scope: str) -> None:
        parts = process_config_path(path)
        data = value
        for key in reversed(parts):
            data = {key: data}
        data = validate_scope(data)
        file = get_scope_filename(scope)
        if fd := read_config_file(file):
            data = merge(fd, data)
        with open(file, "w") as fh:
            yaml.dump({"canary": data}, fh, default_flow_style=False)

    def set_main_options(self, args: argparse.Namespace) -> None:
        """Set main configuration options based on command-line arguments.

        Updates the configuration attributes based on the provided argparse Namespace containing
        command-line arguments.

        Args:
            args: An argparse.Namespace object containing command-line arguments.
        """
        data: dict[str, Any] = {}

        config: dict[str, Any] = data.setdefault("config", {})
        if cache_dir := getattr(args, "cache_dir", None):
            config["cache_dir"] = cache_dir

        logging.set_level(logging.INFO)
        if args.color is not None:
            color.set_color_when(args.color)

        if args.q or args.v:
            level_index: int = log_levels.index(logging.INFO)
            if args.q:
                level_index = min(len(log_levels), level_index + args.q)
            if args.v:
                level_index = max(0, level_index - args.v)
            levelno = log_levels[level_index]
            config["log_level"] = logging.get_level_name(levelno)
            logging.set_level(levelno)

        if args.debug:
            data.setdefault("config", {})["debug"] = True
            data.setdefault("config", {})["log_level"] = "DEBUG"
            logging.set_level(logging.DEBUG)

        if args.config_mods:
            data.update(args.config_mods)

        for section, section_data in data.items():
            if section not in section_schemas:
                raise ValueError(f"Invalid config section: {section!r}")
            schema = section_schemas[section]
            data[section] = schema.validate(section_data)
            self.data[section] = merge(self.data[section], section_data)

        # Put timeouts passed on the command line into the regular configuration
        if t := getattr(args, "timeout", None):
            timeouts: dict[str, float] = config.setdefault("timeout", [])
            for key, val in t.items():
                timeouts[key] = float(val)

        options = data.setdefault("options", {})
        options.update({k: v for k, v in vars(args).items() if v is not None})

        self.options = args

        if args.config_file:
            if fd := read_config_file(args.config_file):
                fd = validate_scope(fd)
                self.data = merge(self.data, fd)

        if self.data["config"]["debug"]:
            logging.set_level(logging.DEBUG)

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


def get_config_scope(scope: str) -> dict[str, Any]:
    """Read the data from config scope ``data``

    By the time the data leaves, it is validated and does not contain a top-level ``canary`` field

    """
    data: dict[str, Any] = {}
    file = get_scope_filename(scope)
    if fd := read_config_file(file):
        data.update(fd)
    return validate_scope(data)


def validate_scope(data: dict[str, Any]) -> dict[str, Any]:
    for section, section_data in data.items():
        if schema := section_schemas.get(section):
            if schema == any_schema:
                data[section] = section_data
            else:
                data[section] = schema.validate(section_data)
        else:
            logger.warning(f"ignoring unrecognized config section: {section}")
    return data


def read_config_file(file: str) -> dict[str, Any] | None:
    """Load configuration settings from ``file``"""
    if not os.path.exists(file):
        return None
    with open(file) as fh:
        fd = yaml.safe_load(fh)
        return fd["canary"] if "canary" in fd else fd


def get_scope_filename(scope: str) -> str:
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


def get_env_scope() -> dict[str, Any]:
    variables = {key: var for key, var in os.environ.items() if key.startswith("CANARY_")}
    if variables:
        variables = environment_variable_schema.validate(variables)
    return variables


def get_workspace_config() -> dict[str, Any]:
    from ..workspace import Workspace

    if path := Workspace.find_workspace():
        if (path / "canary.yaml").exists():
            file = path / "canary.yaml"
            if fd := read_config_file(file):
                return validate_scope(fd)
    return {}


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
    write_directory_tag(path)
