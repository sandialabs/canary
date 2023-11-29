import argparse
import configparser
import copy
import json
import os
import sys
from string import Template
from typing import Any
from typing import Optional
from typing import TextIO
from typing import Union

from ..schemas import any_schema
from ..schemas import config_schema
from ..schemas import machine_schema
from ..schemas import python_schema
from ..schemas import variables_schema
from ..util import tty
from ..util.schema import Schema
from ..util.schema import SchemaError
from ..util.singleton import Singleton
from .machine import machine_config


class ConfigParser(configparser.ConfigParser):
    def optionxform(self, arg):
        return arg


config_dir = ".nvtest"


section_schemas: dict[str, Schema] = {
    "config": config_schema,
    "machine": machine_schema,
    "python": python_schema,
    "variables": variables_schema,
    "system": any_schema,
    "session": any_schema,
}

read_only_sections = ("python",)
valid_scopes = ("defaults", "global", "local", "session", "environment", "command_line")


class Config:
    """Access to configuration values"""

    def __init__(self) -> None:
        machine = machine_config()
        editable_machine_config = {
            "cpu_count": machine.pop("cpu_count"),
            "cores_per_socket": machine.pop("cores_per_socket"),
            "sockets_per_node": machine.pop("sockets_per_node"),
        }
        self.scopes = {
            "defaults": {
                "config": {"debug": False, "log_level": 2},
                "machine": editable_machine_config,
                "system": machine,
                "variables": {},
                "python": {
                    "executable": sys.executable,
                    "version": ".".join(str(_) for _ in sys.version_info[:3]),
                    "version_info": list(sys.version_info),
                },
            }
        }
        home = os.getenv("HOME")
        if home is not None:
            file = os.path.join(home, ".nvtest")
            if os.path.exists(file):
                self.load_config(file, "global")
        if os.path.exists("nvtest.cfg"):
            self.load_config("nvtest.cfg", "local")
        dir = os.getcwd()
        while dir != os.path.sep:
            path = os.path.join(dir, ".nvtest/config")
            if os.path.exists(path):
                self.load_config(path, "session")
                self.set("session:work_tree", dir, scope="session")
                self.set("session:invocation_dir", os.getcwd(), scope="session")
                start = os.path.relpath(dir, os.getcwd()) or "."
                self.set("session:start", start, scope="session")
                break
            dir = os.path.dirname(dir)
        self.load_env_config()

    def load_config(self, file: str, scope: str) -> None:
        self.scopes[scope] = read_config(file)
        if "variables" in self.scopes[scope]:
            for (var, val) in self.scopes[scope]["variables"].items():
                os.environ[var] = val

    def load_env_config(self) -> None:
        if "NVTEST_LOG_LEVEL" in os.environ:
            scope_data = self.scopes.setdefault("environment", {})
            level: int = int(os.environ["NVTEST_LOG_LEVEL"])
            tty.set_log_level(level)
            scope_data.setdefault("config", {})["log_level"] = level
        if os.getenv("NVTEST_DEBUG", "off").lower() in ("on", "1", "true", "yess"):
            scope_data = self.scopes.setdefault("environment", {})
            scope_data.setdefault("config", {})["debug"] = True
            tty.set_debug(True)

    def dump(self, fh: TextIO, scope: Optional[str] = None):
        if scope is not None:
            merged = self.scopes[scope]
        else:
            merged = self.merge()
        for (section, data) in merged.items():
            fh.write(f"[{section}]\n")
            for (key, value) in data.items():
                fh.write(f"{key} = {json.dumps(value)}\n")
            fh.write("\n")

    def set_main_options(self, args: argparse.Namespace) -> None:
        scope_data = self.scopes.setdefault("command_line", {})
        if args.q or args.v:
            user_log_level = tty.default_log_level() - args.q + args.v
            level = max(min(user_log_level, tty.max_log_level()), tty.min_log_level())
            tty.set_log_level(level)
            scope_data.setdefault("config", {})["log_level"] = level
        if args.debug:
            tty.set_debug(True)
            scope_data.setdefault("config", {})["debug"] = True
        for (var, val) in args.env_mods.items():
            os.environ[var] = val
            scope_data.setdefault("variables", {})[var] = val
        for path in args.config_mods:
            self.add(path, scope="command_line")

    def merge(self, skip_scopes: Optional[list[str]] = None) -> dict:
        scopes = list(self.scopes.keys())
        merged = dict(self.scopes[scopes.pop(0)])
        for scope in scopes:
            if skip_scopes is not None and scope in skip_scopes:
                continue
            scope_data = dict(self.scopes[scope])
            merged = _merge(merged, scope_data)
        return merged

    def highest_precedence_scope(self) -> dict:
        scope = next(reversed(self.scopes.keys()))
        return self.scopes[scope]

    def validate_section_name(self, section: str) -> None:
        if section not in section_schemas:
            raise ValueError(f"{section!r} is not a valid configuration section")

    def validate_scope(self, scope: Union[str, None]) -> dict:
        if scope is None:
            return self.highest_precedence_scope()
        elif scope in self.scopes:
            return self.scopes[scope]
        elif scope in valid_scopes:
            return self.scopes.setdefault(scope, {})
        else:
            raise ValueError(f"{scope!r} is not a valid configuration scope")

    def get_config(self, section: str, scope: Optional[str] = None) -> dict:
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
            cfg_scopes = [self.validate_scope(scope)]
        merged_section: dict[str, Any] = {}
        for cfg_scope in cfg_scopes:
            data = cfg_scope.get(section)
            if not data or not isinstance(data, dict):
                continue
            merged_section = _merge(merged_section, {section: data})
        if section not in merged_section:
            return {}
        return merged_section[section]

    def get(self, path: str, default: Any = None, scope: Optional[str] = None) -> Any:
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

    def set(self, path: str, value: Any, scope: Optional[str] = None) -> None:
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

    def add(self, fullpath: str, scope: Optional[str] = None) -> None:
        """Add the given configuration to the specified config scope."""

        components = parse_config_path(fullpath)

        path = ""
        has_existing_value = True
        for idx, name in enumerate(components[:-1]):
            # First handle double colons in constructing path
            colon = ":" if path else ""
            path += colon + name

            # Test whether there is an existing value at this level
            existing = get(path, scope=scope)

            if existing is None:
                has_existing_value = False
                # construct value from this point down
                value = components[-1]
                try:
                    value = json.loads(value)
                except json.decoder.JSONDecodeError:
                    pass
                for component in reversed(components[idx + 1 : -1]):
                    value = {component: value}
                break

        if has_existing_value:
            path, _, value = fullpath.rpartition(":")
            value = json.loads(value)
            existing = get(path, scope=scope)

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
        scope_data = self.validate_scope(scope)
        scope_data[section] = update_data

    def describe(self, section: Optional[str] = None) -> str:
        import yaml

        if section is not None:
            merged = {section: self.get_config(section)}
        else:
            merged = self.merge()
        return yaml.dump(merged, default_flow_style=False)


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


def read_config(file: str, tolerant: bool = False) -> dict:
    cfg = ConfigParser()
    cfg.read(file)
    data: dict[str, Any] = {}
    for section in cfg.sections():
        if tolerant and section in read_only_sections:
            continue
        section_data = data.setdefault(section, {})
        for (key, value) in cfg.items(section, raw=True):
            value = Template(value).safe_substitute(os.environ)
            try:
                section_data[key] = json.loads(value)
            except json.decoder.JSONDecodeError:
                section_data[key] = value
        if section in section_schemas:
            schema = section_schemas[section]
            try:
                schema.validate({section: section_data})
            except SchemaError as e:
                raise ConfigSchemaError(file, e.args[0]) from None
    return data


def parse_config_path(path):
    """Parse the path argument to various configuration methods.
    Splits ``path`` on ':'

    """
    if path.startswith(":"):
        raise ValueError(f"Illegal leading `:' in path {path:r}")
    return [_.strip() for _ in path.split(":") if _.split()]


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


config = Singleton(Config)


def dump(fh: TextIO, scope: Optional[str] = None):
    return config.dump(fh, scope=scope)


def set_main_options(args: argparse.Namespace) -> None:
    return config.set_main_options(args)


def get(path: str, default: Any = None, scope: Optional[str] = None) -> Any:
    return config.get(path, default=default, scope=scope)


def set(path: str, value: Any, scope: Optional[str] = None) -> None:
    return config.set(path, value, scope=scope)


def describe(section: Optional[str] = None) -> str:
    return config.describe(section=section)


def add(fullpath: str, scope: Optional[str] = None) -> None:
    config.add(fullpath, scope=scope)


def has_scope(scope: str) -> bool:
    return scope in config.scopes
