import argparse
import configparser
import copy
import json
import os
import sys
from string import Template
from typing import Any
from typing import TextIO

from ..third_party.schema import Schema
from ..third_party.schema import SchemaError
from ..util import logging
from ..util.misc import ns2dict
from ..util.singleton import Singleton
from ..util.time import time_in_seconds
from . import machine
from .schemas import any_schema
from .schemas import batch_schema
from .schemas import build_schema
from .schemas import config_schema
from .schemas import machine_schema
from .schemas import python_schema
from .schemas import test_schema
from .schemas import variables_schema


class ConfigParser(configparser.ConfigParser):
    def optionxform(self, arg):
        return arg


config_dir = ".nvtest"


section_schemas: dict[str, Schema] = {
    "build": build_schema,
    "batch": batch_schema,
    "config": config_schema,
    "machine": machine_schema,
    "python": python_schema,
    "variables": variables_schema,
    "session": any_schema,
    "system": any_schema,
    "option": any_schema,
    "test": test_schema,
}

read_only_sections = ("python",)
valid_scopes = ("defaults", "global", "local", "session", "environment", "command_line")

invocation_dir = os.getcwd()
work_dir = invocation_dir


class Config:
    """Access to configuration values"""

    fb = f"config.{sys.implementation.cache_tag}.p"

    def __init__(self, state: dict | None = None) -> None:
        self.scopes: dict
        if state is not None:
            self.scopes = state["scopes"]
            for scope_data in self.scopes.values():
                if scope_data.get("variables"):
                    for var, val in scope_data["variables"].items():
                        os.environ[var] = val
            level_name = self.get("config:log_level")
            logging.set_level(logging.get_level(level_name))
        else:
            self.scopes = {
                "defaults": {
                    "config": {
                        "debug": False,
                        "no_cache": False,
                        "log_level": "INFO",
                    },
                    "test": {"timeout": {"fast": 120.0, "long": 15 * 60.0, "default": 7.5 * 60.0}},
                    "batch": {"length": 30 * 60},
                    "machine": machine.machine_config(),
                    "system": machine.system_config(),
                    "variables": {},
                    "python": {
                        "executable": sys.executable,
                        "version": ".".join(str(_) for _ in sys.version_info[:3]),
                        "version_info": list(sys.version_info),
                    },
                }
            }
            file = self.config_file("global")
            if file is not None and os.path.exists(file):
                self.load_config(file, "global")
            file = self.config_file("local")
            if file is not None and os.path.exists(file):
                self.load_config(file, "local")
            self.load_config_from_env()

    def config_file(self, scope) -> str | None:
        if scope == "global":
            if "NVTEST_GLOBAL_CONFIG" in os.environ:
                return os.environ["NVTEST_GLOBAL_CONFIG"]
            elif "HOME" in os.environ:
                home = os.environ["HOME"]
                return os.path.join(home, ".nvtest")
        elif scope == "local":
            return os.path.abspath("./nvtest.cfg")
        elif scope == "session":
            dir = self.get("session:root")
            if not dir:
                raise ValueError("session:root has not been set")
            return os.path.join(dir, config_dir, "config")
        return None

    def load_config(self, file: str, scope: str) -> None:
        self.scopes[scope] = read_config(file)
        if "variables" in self.scopes[scope]:
            for var, val in self.scopes[scope]["variables"].items():
                os.environ[var] = val
        if self.scopes[scope].get("test", {}).get("timeout"):
            for key, val in self.scopes[scope]["test"]["timeout"].items():
                self.scopes[scope]["test"]["timeout"][key] = time_in_seconds(val)

    def load_config_from_env(self) -> None:
        for varname, raw_value in os.environ.items():
            if not varname.startswith("NVTEST_"):
                continue
            scope_data: dict[str, Any] = self.scopes.setdefault("environment", {})
            match varname.lower().split("_", 2)[1:]:
                case ["config", "debug"] | ["debug"]:
                    if raw_value.lower() in ("on", "1", "true", "yes"):
                        scope_data.setdefault("config", {})["debug"] = True
                        scope_data.setdefault("config", {})["log_level"] = "DEBUG"
                        logging.set_level(logging.DEBUG)
                case ["config", "log_level"] | ["log_level"]:
                    level = logging.get_level(raw_value.upper())
                    logging.set_level(level)
                    scope_data.setdefault("config", {})["log_level"] = raw_value.upper()
                case ["config", "no_cache"] | ["no_cache"]:
                    scope_data.setdefault("config", {})["no_cache"] = True
                case ["batch", "length"]:
                    scope_data.setdefault("batch", {})["length"] = time_in_seconds(raw_value)
                case ["machine", key]:
                    scope_data.setdefault("machine", {})[key] = int(raw_value)
                case ["test", keys]:
                    field, key = keys.split("_", 1)
                    test_data = scope_data.setdefault("test", {})
                    if field == "timeout":
                        test_data.setdefault(field, {})[key] = time_in_seconds(raw_value)

    def dump(self, file: TextIO) -> None:
        state = self.getstate()
        json.dump({"scopes": state}, file, indent=2)

    def loadstate(self, state: dict[str, Any]) -> None:
        state["scopes"].pop("command_line", None)
        self.scopes.update(state["scopes"])

    def load(self, file: TextIO) -> None:
        state = json.load(file)
        self.loadstate(state)

    def getstate(self) -> dict[str, Any]:
        return dict(self.scopes)

    def save(self, fh: TextIO, *, scope: str) -> None:
        data = self.scopes[scope]
        table = self.flatten(data)
        for section in sorted(table):
            fh.write(f"[{section}]\n")
            subsections: list[str] = []
            for key, value in table[section].items():
                if isinstance(value, dict):
                    subsections.append(key)
                else:
                    fh.write(f"{key} = {json.dumps(value)}\n")
            fh.write("\n")
            for subsection in subsections:
                fh.write(f"[{section}:{subsection}]\n")
                for key, value in table[section][subsection].items():
                    fh.write(f"{key} = {json.dumps(value)}\n")
                fh.write("\n")

    @staticmethod
    def flatten(mapping: dict) -> dict:
        fd = {}
        for s, sd in mapping.items():
            if not isinstance(sd, dict):
                fd[s] = sd
            else:
                for p, pd in sd.items():
                    if not isinstance(pd, dict):
                        fd.setdefault(s, {})[p] = pd
                    else:
                        fd[f"{s}:{p}"] = Config.flatten(pd)
        return fd

    def set_main_options(self, args: argparse.Namespace) -> None:
        global work_dir
        if args.C:
            work_dir = args.C
        scope_data: dict = self.scopes.setdefault("command_line", {})
        logging.set_level(logging.INFO)
        if args.q or args.v:
            i = min(max(2 - args.q + args.v, 0), 4)
            levels = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.TRACE)
            logging.set_level(levels[i])
            level_name = logging.get_level_name(levels[i])
            scope_data.setdefault("config", {})["log_level"] = level_name
        if args.debug:
            logging.set_level(logging.DEBUG)
            scope_data.setdefault("config", {})["debug"] = True
            scope_data.setdefault("config", {})["log_level"] = "DEBUG"
        for var, val in args.env_mods.get("session", {}).items():
            os.environ[var] = val
            scope_data.setdefault("variables", {})[var] = val
        for path in args.config_mods:
            self.add(path, scope="command_line")
        option_data: dict = scope_data.setdefault("option", {})
        option_data["main"] = ns2dict(args)

    def set_command_options(self, command_name: str, args: argparse.Namespace) -> None:
        scope_data: dict = self.scopes.setdefault("command_line", {})
        option_data: dict = scope_data.setdefault("option", {})
        main_option_data: dict = option_data.get("main", {})
        options = ns2dict(args)
        options.pop("command", None)
        options.pop("resource_setter", None)
        for key, val in main_option_data.items():
            if key in options and options[key] == val:
                options.pop(key, None)
        option_data[command_name] = options

    def merge(self, skip_scopes: list[str] | None = None) -> dict:
        scopes = list(self.scopes.keys())
        merged = dict(self.scopes[scopes.pop(0)])
        for scope in scopes:
            if skip_scopes is not None and scope in skip_scopes:
                continue
            scope_data = dict(self.scopes[scope])
            merged = _merge(merged, scope_data)
        return merged

    def highest_precedence_scope(self) -> str:
        return next(reversed(self.scopes.keys()))

    def validate_section_name(self, section: str) -> None:
        if section not in section_schemas:
            raise ValueError(f"{section!r} is not a valid configuration section")

    def validate_scope_name(self, scope: str | None) -> None:
        if scope is None:
            return
        if scope not in self.scopes and scope not in valid_scopes:
            raise ValueError(f"{scope!r} is not a valid configuration scope")

    def get_scope_data(self, scope: str | None) -> dict:
        if scope is None:
            scope = self.highest_precedence_scope()
            return self.scopes[scope]
        elif scope in self.scopes:
            return self.scopes[scope]
        elif scope in valid_scopes:
            return self.scopes.setdefault(scope, {})
        else:
            raise ValueError(f"{scope!r} is not a valid configuration scope")

    def get_config(self, section: str, scope: str | None = None) -> dict:
        """Get configuration settings for a section.

        If ``scope`` is ``None`` or not provided, return the merged contents
        of all of nevada's configuration scopes.  If ``scope`` is provided,
        return only the configuration as specified in that scope.

        """
        self.validate_section_name(section)
        cfg_scopes: list[dict[str, Any]]
        if scope is None:
            cfg_scopes = list(self.scopes.values())
        else:
            cfg_scopes = [self.get_scope_data(scope)]
        merged: dict[str, Any] = {}
        for cfg_scope in cfg_scopes:
            data = cfg_scope.get(section)
            if not data or not isinstance(data, dict):
                continue
            merged = _merge(merged, {section: data})
        return {} if section not in merged else merged[section]

    def get(self, path: str, default: Any | None = None, scope: str | None = None) -> Any:
        """Get a config section or a single value from one.

        Accepts a path syntax that allows us to grab nested config map
        entries.  Getting the 'config' section would look like::

            nvtest.config.get('config')

        and the ``debug`` section in the ``config`` scope would be::

            nvtest.config.get('config:debug')

        We use ``:`` as the separator, like YAML objects.
        """
        parts = parse_config_path(path)
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

    def pop(self, path: str, scope: str | None = None) -> Any:
        pass

    def set(self, path: str, value: Any, scope: str | None = None) -> None:
        """Convenience function for setting single config values

        Accepts the path syntax described in ``get()``.
        """

        if ":" not in path:
            # handle bare section name as path
            self.update_config(path, value, scope=scope)
            return

        parts = parse_config_path(path)
        section = parts.pop(0)
        if section in read_only_sections:
            raise ValueError(f"{section!r} is a read-only scope")
        self.validate_section_name(section)
        if section == "session":
            if scope is None:
                scope = "session"
            if scope != "session":
                raise ValueError("session section must set into session scope")
        section_data = self.get_config(section, scope=scope)
        data = section_data
        while len(parts) > 1:
            key = parts.pop(0)
            new = data[key]
            if isinstance(new, dict):
                new = dict(new)
                # reattach to parent object
                data[key] = new
            data = new
        # update new value
        data[parts[0]] = value
        self.update_config(section, section_data, scope=scope)

    def add(self, fullpath: str, scope: str | None = None) -> None:
        """Add the given configuration to the specified config scope."""

        components = parse_config_path(fullpath)

        path = ""
        has_existing_value = True
        for idx, name in enumerate(components[:-1]):
            # First handle double colons in constructing path
            colon = ":" if path else ""
            path += colon + name

            # Test whether there is an existing value at this level
            existing = self.get(path, scope=scope)

            if existing is None:
                has_existing_value = False
                # construct value from this point down
                value = safe_loads(components[-1])
                for component in reversed(components[idx + 1 : -1]):
                    value = {component: value}
                break

        if has_existing_value:
            path, _, value = fullpath.rpartition(":")
            value = safe_loads(value)
            existing = self.get(path, scope=scope)

        # append values to lists
        if isinstance(existing, list) and not isinstance(value, list):
            value = [value]

        # merge value into existing
        new = _merge(existing, value)
        self.set(path, new, scope=scope)

    def update_config(self, section, update_data, scope=None):
        """Update the configuration file for a particular scope.

        Overwrites contents of a section in a scope with update_data,
        then writes out the config file.

        update_data should have the top-level section name stripped off
        (it will be re-added).  Data itself can be a list, dict, or any
        other yaml-ish structure.

        Configuration scopes that are still written in an old schema
        format will fail to update unless ``force`` is True.

        Args:
            section (str): section of the configuration to be updated
            update_data (dict): data to be used for the update
            scope (str): scope to be updated
        """
        self.validate_section_name(section)
        self.validate_scope_name(scope)
        scope_data = self.get_scope_data(scope)
        if section == "machine":
            self.validate_machine_config_and_fill_missing(update_data)
        section_schemas[section].validate({section: update_data})
        scope_data[section] = update_data

    def validate_machine_config_and_fill_missing(self, data: dict) -> None:
        if "node_count" in data and data["node_count"] < 1:
            raise ValueError(f"node_count must be at least one ({data['node_count']} < 1)")

        if "cpus_per_node" in data and data["cpus_per_node"] < 1:
            raise ValueError(f"cpus_per_node must be at least one ({data['cpus_per_node']} < 0)")

        if "gpus_per_node" in data and data["gpus_per_node"] < 0:
            raise ValueError(f"gpus_per_node must be positive ({data['gpus_per_node']} < 0)")

    def describe(self, section: str | None = None) -> str:
        if section is not None:
            merged = {section: self.get_config(section)}
        else:
            merged = self.merge()
        try:
            import yaml

            return yaml.dump(merged, default_flow_style=False)
        except ImportError:
            return json.dumps(merged, indent=2)


def _merge(dest, source):
    """Merges source into dest; entries in source take precedence over dest.

    This routine may modify dest and should be assigned to dest, in
    case dest was None to begin with, e.g.:

       dest = merge(dest, source)

    In the result, elements from lists from ``source`` will appear before
    elements of lists from ``dest``. Likewise, when iterating over keys
    or items in merged ``OrderedDict`` objects, keys from ``source`` will
    appear before keys from ``dest``.

    Config file authors can optionally end any attribute in a dict
    with `::` instead of `:`, and the key will override that of the
    parent instead of merging.
    """

    def they_are(t):
        return isinstance(dest, t) and isinstance(source, t)

    # If source is None, overwrite with source.
    if source is None:
        return None

    # Source list is prepended (for precedence)
    if they_are(list):
        dest[:] = source + [x for x in dest if x not in source]
        return dest

    # Source dict is merged into dest.
    elif they_are(dict):
        # save dest keys to reinsert later -- this ensures that  source items
        # come *before* dest in OrderdDicts
        dest_keys = [dk for dk in dest.keys() if dk not in source]

        for sk, sv in source.items():
            # always remove the dest items. Python dicts do not overwrite
            # keys on insert, so this ensures that source keys are copied
            # into dest along with mark provenance (i.e., file/line info).
            merge_objects = sk in dest
            old_dest_value = dest.pop(sk, None)

            if merge_objects:
                dest[sk] = _merge(old_dest_value, sv)
            else:
                # if sk ended with ::, or if it's new, completely override
                dest[sk] = copy.deepcopy(sv)

        # reinsert dest keys so they are last in the result
        for dk in dest_keys:
            dest[dk] = dest.pop(dk)

        return dest

    # If we reach here source and dest are either different types or are
    # not both lists or dicts: replace with source.
    return copy.copy(source)


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


def expandvars(arg: str, mapping: dict) -> str:
    t = Template(arg)
    return t.safe_substitute(mapping)


def read_config(file: str) -> dict:
    cfg = ConfigParser()
    cfg.read(file)
    data: dict[str, Any] = {}
    variables = dict(os.environ)
    # make variables available in other config sections
    if cfg.has_section("variables"):
        section_data = data.setdefault("variables", {})
        for key, raw_value in cfg.items("variables", raw=True):
            value = expandvars(raw_value, variables)
            section_data[key] = str(safe_loads(value))
            variables[key] = section_data[key]
    for section in cfg.sections():
        if section == "variables":
            continue
        section_data = data.setdefault(section, {})
        for key, raw_value in cfg.items(section, raw=True):
            value = expandvars(raw_value, variables)
            section_data[key] = safe_loads(value)
    config_data: dict[str, Any] = {}
    # expand any keys given as a:b:c
    for path, section_data in data.items():
        if path in section_schemas:
            config_data[path] = section_data
        elif ":" in path:
            parts = parse_config_path(path)
            if parts[0] not in section_schemas:
                logging.warning(f"ignoring unrecognized config section: {parts[0]}")
                continue
            x = config_data.setdefault(parts[0], {})
            for part in parts[1:]:
                x = x.setdefault(part, {})
            x.update(section_data)
        else:
            logging.warning(f"ignoring unrecognized config section: {path}")
    for section, section_data in config_data.items():
        schema = section_schemas[section]
        try:
            schema.validate({section: section_data})
        except SchemaError as e:
            raise ConfigSchemaError(file, e.args[0]) from None
    return config_data


def parse_config_path(path):
    """Parse the path argument to various configuration methods.
    Splits ``path`` on ':'

    """
    if path.startswith(":"):
        raise ValueError(f"Illegal leading `:' in path {path:r}")
    parts = [_.strip() for _ in path.split(":") if _.split()]
    if parts and "=" in parts[-1]:
        parts = parts[:-1] + parts[-1].split("=", 1)
    return parts


class IllegalConfiguration(Exception):
    def __init__(self, option, message=None):
        msg = f"Illegal configuration setting: {option}"
        if message:
            msg += f". {message}"
        super().__init__(msg)


class ConfigSchemaError(Exception):
    def __init__(self, filename, error):
        msg = f"Schema error encountered in {filename}: {error}"
        super().__init__(msg)


def find_session_root() -> str | None:
    path = os.getcwd()
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


def factory() -> Config:
    root = find_session_root()
    if root:
        # Setting up test cases and several other operations are done in a
        # multiprocessing Pool so we reload the configuration that existed when that pool
        # was created
        file = os.path.join(root, ".nvtest/config")
        if os.path.exists(file):
            with open(file) as fh:
                state = json.load(fh)
                return Config(state=state)
        logging.warning("We appear to be running in a session but no config was found")
    return Config()


config = Singleton(factory)


def dump(fh: TextIO) -> None:
    config.dump(fh)


def load(fh: TextIO) -> None:
    config.load(fh)


def save(fh: TextIO, *, scope: str) -> None:
    return config.save(fh, scope=scope)


def config_file(scope: str) -> str | None:
    return config.config_file(scope)


def set_main_options(args: argparse.Namespace) -> None:
    return config.set_main_options(args)


def set_command_options(command_name: str, args: argparse.Namespace) -> None:
    return config.set_command_options(command_name, args)


def get(path: str, default: Any | None = None, scope: str | None = None) -> Any:
    return config.get(path, default=default, scope=scope)


def getoption(option: str, default: Any | None = None, scope: str | None = None) -> Any:
    if ":" not in option:
        option = f"main:{option}"
    return config.get(f"option:{option}", default=default, scope=scope)


def set(path: str, value: Any, scope: str | None = None) -> None:
    return config.set(path, value, scope=scope)


def pop(path: str, scope: str | None = None) -> Any:
    return config.pop(path, scope=scope)


def describe(section: str | None = None) -> str:
    return config.describe(section=section)


def add(fullpath: str, scope: str | None = None) -> None:
    config.add(fullpath, scope=scope)


def has_scope(scope: str) -> bool:
    return scope in config.scopes


def instance():
    return config._instance
