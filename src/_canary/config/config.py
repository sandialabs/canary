# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import sys
from pathlib import Path
from string import Template
from typing import IO
from typing import Any
from typing import Literal

import yaml
from schema import Optional
from schema import Schema

from ..pluginmanager import CanaryPluginManager
from ..resource_pool.manager import ResourceManager
from ..util import json_helper as json
from ..util import logging
from ..util.collections import merge
from ..util.compression import deserialize
from ..util.compression import serialize
from ..util.rich import set_color_when
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
CONFIG_ENV_CFG64 = "CANARYCFG64"
ConfigScopes = Literal["site", "global", "local"]

logger = logging.get_logger(__name__)


def default_config_values() -> dict[str, Any]:
    uname = os.uname()
    defaults = {
        "debug": False,
        "log_level": "INFO",
        "no_pager": False,
        "plugins": [],
        "environment": {"prepend-path": {}, "append-path": {}, "set": {}, "unset": []},
        "workspace": {
            "view": {"name": "TestResults", "mode": "symlink", "when": "always", "only": "all"}
        },
        "run": {
            "default_tag": ":all:",
            "timeout": {
                "session": -1.0,
                "multiplier": 1.0,
                "fast": 120.0,
                "default": 300.0,
                "long": 900.0,
                "queue": 4.0 * 60.0 * 60.0,
            },
            "cache": {"dir": None},
        },
        "scratch": {},
        "system": {
            "sysname": uname.sysname,
            "nodename": uname.nodename,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
        },
    }
    return defaults


class Config:
    def __init__(self, loadini: bool = True) -> None:
        self.invocation_dir = invocation_dir
        self.pluginmanager: CanaryPluginManager = CanaryPluginManager.factory()
        self.pluginmanager.hook.canary_addhooks(pluginmanager=self.pluginmanager)
        self.resource_manager: ResourceManager = ResourceManager(self)
        self.data: dict[str, Any] = {}
        self.options: argparse.Namespace = argparse.Namespace()
        if loadini:
            self.load()

    def load(self) -> None:
        data: dict[str, Any] = default_config_values()
        for name in ("site", "global", "local"):
            try:
                scope = get_config_scope_data(name)
            except LocalScopeDoesNotExistError:
                continue
            data = merge(data, scope)  # type: ignore
        if env_scope := get_env_scope():
            data = merge(data, env_scope)  # type: ignore
        bootstrap = Schema({Optional("plugins"): [str]}, ignore_extra_keys=True).validate(data)
        # Persisted plugins here come from a workspace config.yaml; relative
        # path plugins are resolved against the workspace anchor (the directory
        # containing .canary) per the hard rule for that file.
        base = workspace_anchor()
        for plugin in bootstrap.get("plugins", []):
            self._consider_persisted_plugin(plugin, base=base)
        self.pluginmanager.hook.canary_addconfig(config=self)
        self.resource_manager.clear()
        self.data = config_schema.validate(data)
        if self.get("debug"):
            logging.set_level(logging.DEBUG)

    @staticmethod
    def factory() -> "Config":
        logging.setup_logging()
        config = Config(loadini=False)
        if f := os.getenv(CONFIG_ENV_FILENAME):
            with open(f, "r") as fh:
                snapshot = json.load(fh)
            config._apply_snapshot(snapshot)
            config._load_plugins_from_data()
        elif envcfg := os.getenv(CONFIG_ENV_CFG64):
            snapshot = deserialize(envcfg)
            config._apply_snapshot(snapshot)
            config._load_plugins_from_data()
        else:
            config.load()
        Config._set_log_level(config)
        return config

    @staticmethod
    def from_snapshot(snapshot: dict[str, Any]) -> "Config":
        logging.setup_logging()
        config = Config(loadini=False)
        config._apply_snapshot(snapshot)
        config._load_plugins_from_data()
        Config._set_log_level(config)
        return config

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.invocation_dir = snapshot["invocation_dir"]
        self._restore_sys_path(snapshot.get("sys_path", []))
        self.options = argparse.Namespace(**snapshot["options"])
        self.data.clear()
        self.data.update(snapshot["data"])
        self.resource_manager.clear()
        if resource_manager_snapshot := snapshot.get("resource_manager"):
            self.resource_manager.load_snapshot(resource_manager_snapshot)

    @staticmethod
    def _restore_sys_path(entries: list[str]) -> None:
        """Prepend snapshot ``sys.path`` entries missing from the child.

        A snapshot must be self-contained: a consumer (an HPC batch child, a
        flux job, a worker process) may run from a different working directory
        and without the parent's ``PYTHONPATH``, so plugins listed in the
        snapshot could otherwise be unimportable.  Prepending the parent's
        (absolute) path entries makes them importable without relying on the
        child's environment or on reading a workspace config file.
        """
        for entry in reversed(entries):
            if entry and entry not in sys.path:
                sys.path.insert(0, entry)

    def _load_plugins_from_data(self) -> None:
        # Load plugins listed in current self.data, then let them add config sections.
        # These come from a config SNAPSHOT (an HPC batch child, flux job, or
        # worker), which may run from a different cwd than the original run, so
        # relative plugin paths are resolved against the run's invocation_dir
        # (carried in the snapshot) — the same base used for snapshot sys.path.
        base = self.invocation_dir
        for plugin in self.data.get("plugins", []):
            self._consider_persisted_plugin(plugin, base=base)
        self.pluginmanager.hook.canary_addconfig(config=self)

    def _consider_persisted_plugin(self, plugin: str, *, base: str | Path | None) -> None:
        """Load a plugin recorded in persisted config, best-effort.

        Relative path plugins are resolved against *base* (see
        :func:`resolve_plugin`).  A load failure is downgraded to a warning
        rather than crashing every command in the workspace: a stale or
        unresolvable persisted plugin must not brick the CLI.  Plugins requested
        on the CURRENT command line still surface hard errors because they flow
        through ``consider_plugin`` directly.
        """
        resolved = resolve_plugin(plugin, base=base)
        try:
            self.pluginmanager.consider_plugin(resolved)
        except Exception as e:
            logger.warning(
                f"failed to load plugin {plugin!r} recorded in workspace config: {e}; "
                "continuing without it (pass -p explicitly to force an error)"
            )

    @staticmethod
    def _set_log_level(config: "Config") -> None:
        log_level = config.get("log_level")
        if logging.get_level_name(logger.level) != log_level:
            logging.set_level(log_level)

    def dump(self, file: IO[Any]) -> None:
        file.write(json.dumps(self.snapshot(), indent=2))

    def snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "invocation_dir": str(self.invocation_dir),
            "options": vars(self.options),
            "data": self.data,
            "resource_manager": self.resource_manager.snapshot(),
            "sys_path": self._snapshot_sys_path(),
        }
        return snapshot

    def _snapshot_sys_path(self) -> list[str]:
        """Capture ``sys.path`` as absolute entries for a self-contained snapshot.

        Relative entries are resolved against the invocation directory so a
        consumer running from a different working directory resolves them the
        same way the parent did.
        """
        invocation_dir = str(self.invocation_dir)
        resolved: list[str] = []
        for entry in sys.path:
            if not entry:
                continue
            if os.path.isabs(entry):
                resolved.append(entry)
            else:
                resolved.append(os.path.abspath(os.path.join(invocation_dir, entry)))
        return resolved

    def serialize(self) -> str:
        return serialize(self.snapshot())

    def getoption(self, name: str, default: Any = None) -> Any:
        return getattr(self.options, name, default)

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

    def add_section(self, name: str, schema: Schema) -> None:
        config_schema._schema.update({Optional(name): schema})

    def set(self, path: str, value: Any, *, replace: bool = False) -> None:
        parts = process_config_path(path)
        data = value
        for key in reversed(parts):
            data = {key: data}

        data = config_schema.validate(data)

        if parts[0] == "environment":
            self.apply_environment_mods(data["environment"])

        if replace:
            validated_value = data
            for key in parts:
                validated_value = validated_value[key]

            target = self.data
            for key in parts[:-1]:
                child = target.get(key)
                if not isinstance(child, dict):
                    child = {}
                    target[key] = child
                target = child

            target[parts[-1]] = validated_value
        else:
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

        if getattr(args, "no_pager", None):
            data["no_pager"] = True

        if args.config_mods:
            data.update(args.config_mods)
            if envmods := args.config_mods.get("environment"):
                self.apply_environment_mods(envmods)

        # Put timeouts passed on the command line into the regular configuration
        if t := getattr(args, "timeout", None):
            runcfg: dict[str, Any] = data.setdefault("run", {})
            timeouts: dict[str, float] = runcfg.setdefault("timeout", {})
            for key, val in t.items():
                timeouts[key] = float(val)

        self.data = merge(self.data, data)  # type: ignore
        self.options = args
        self.resource_manager.clear()

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
    return data


def read_config_file(file: str | Path) -> dict[str, Any] | None:
    """Load configuration settings from ``file``"""
    file = Path(file)
    if not file.exists():
        return None
    fd: Any
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


def is_plugin_path(name: str) -> bool:
    """Return True if *name* denotes a filesystem path rather than a dotted module.

    A plugin spec is treated as a path when it looks like a ``.py`` file or when
    it contains a path separator (``os.sep`` or ``/``).  Bare dotted module names
    (e.g. ``mypkg.hooks``) are never treated as paths.  A leading ``no:`` prefix
    (used to *block* a plugin) is stripped before the test.
    """
    if name.startswith("no:"):
        name = name[3:]
    if name.endswith(".py"):
        return True
    return os.sep in name or "/" in name


def normalize_plugin_for_storage(name: str, *, anchor: str | Path) -> str:
    """Normalize a plugin spec for persistence in a workspace ``config.yaml``.

    Path-like plugins are stored RELATIVE to the workspace *anchor* (the
    directory containing ``.canary``) when they live inside that tree, so the
    same workspace resolves them regardless of the absolute mount point through
    which it is accessed (e.g. ``/gpfs`` on the host vs ``/projects`` in a
    container).  Paths outside the anchor tree are stored as absolute paths.
    Dotted module names and ``no:`` block directives are stored verbatim.
    """
    if not is_plugin_path(name):
        return name
    prefix = ""
    raw = name
    if raw.startswith("no:"):
        prefix, raw = "no:", raw[3:]
    abspath = os.path.abspath(os.path.join(str(anchor), raw)) if not os.path.isabs(raw) else raw
    anchor_abs = os.path.abspath(str(anchor))
    try:
        if os.path.commonpath([abspath, anchor_abs]) == anchor_abs:
            return f"{prefix}{os.path.relpath(abspath, anchor_abs)}"
    except ValueError:
        # Different drives / uncomparable paths — fall back to absolute.
        pass
    return f"{prefix}{abspath}"


def resolve_plugin(name: str, *, base: str | Path | None) -> str:
    """Resolve a persisted plugin spec to something loadable in this process.

    A relative *path* plugin is resolved against *base* (an absolute directory).
    Absolute paths, dotted module names, and ``no:`` block directives are
    returned unchanged.  Returns *name* unchanged when *base* is ``None``.

    The correct *base* depends on the source of the persisted spec:

    * a workspace ``config.yaml`` — the workspace anchor (directory containing
      ``.canary``); this is the hard rule for relative paths in that file.
    * a config *snapshot* (``config.json`` / ``CANARYCFG64``) consumed by an HPC
      batch child, flux job, or worker — the run's ``invocation_dir``.  Such a
      child typically runs from a different cwd (its batch/workspace dir), so a
      relative path must be resolved against the original invocation directory,
      exactly as snapshot ``sys.path`` entries are (see ``_snapshot_sys_path``).
    """
    if base is None or not is_plugin_path(name):
        return name
    prefix = ""
    raw = name
    if raw.startswith("no:"):
        prefix, raw = "no:", raw[3:]
    if os.path.isabs(raw):
        return name
    return f"{prefix}{os.path.abspath(os.path.join(str(base), raw))}"


def workspace_anchor() -> Path | None:
    """Return the workspace anchor (directory containing ``.canary``) or None."""
    from ..workspace import Workspace

    return Workspace.find_anchor()


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


class LocalScopeDoesNotExistError(Exception):
    pass
