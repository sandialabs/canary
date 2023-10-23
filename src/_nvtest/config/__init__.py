import argparse
import configparser
import errno
import json
import os
import sys
from string import Template
from types import SimpleNamespace
from typing import Any
from typing import Optional
from typing import TextIO
from typing import Union

from ..schemas import config_schema
from ..util import tty
from ..util.misc import ns2dict
from ..util.schema import SchemaError
from ..util.tty.color import colorize
from .argparsing import make_argument_parser
from .machine import editable_properties as editable_machine_properties
from .machine import machine_config

user_config_filename = "nvtest.cfg"


def setdefault(namespace: argparse.Namespace, attr: str, default: Any) -> Any:
    try:
        return getattr(namespace, attr)
    except AttributeError:
        setattr(namespace, attr, default)
        return default


class ConfigParser(configparser.ConfigParser):
    def optionxform(self, arg):
        return arg


class Config:
    """Access to configuration values"""

    sections = ("config", "machine", "variables", "python")
    editable_sections = ("config", "machine", "variables")

    def __init__(self, user_config_file: Optional[str] = None):
        self.config = SimpleNamespace(debug=False, log_level=2, user_cfg_file=None)
        self.option: Optional[argparse.Namespace] = None
        self.machine = machine_config()
        self.variables: dict[str, str] = {}
        self.python = SimpleNamespace(
            executable=sys.executable,
            version=".".join(str(_) for _ in sys.version_info[:3]),
            version_info=list(sys.version_info),
        )
        self.load_user_config_file(config_file=user_config_file)

    @classmethod
    def load(cls, file: str):
        self = cls(user_config_file=file)
        return self

    def find_user_config_file(self) -> Union[str, None]:
        cwd = os.getcwd()
        f: str = user_config_filename
        home = os.path.expanduser("~")
        p = make_argument_parser()
        opts = p.preparse()
        if opts.config_file == "none":
            return None
        elif opts.config_file:
            return opts.config_file
        elif os.path.exists(os.path.join(cwd, ".nvtest", f)):
            return os.path.join(cwd, ".nvtest", f)
        elif os.path.exists(os.path.join(cwd, f)):
            return os.path.join(cwd, f)
        elif os.path.exists(os.path.join(home, ".config", f)):
            return os.path.join(home, ".config", f)
        elif os.path.exists(os.path.join(home, "." + f)):
            return os.path.join(home, "." + f)
        return None

    @staticmethod
    def loadcfg(file: str) -> dict[str, Any]:
        cfg = ConfigParser()
        cfg.read(file)
        data: dict[str, Any] = {}
        for section in cfg.sections():
            sdata = data.setdefault(section, {})
            for (key, value) in cfg.items(section):
                try:
                    sdata[key] = json.loads(value)
                except json.decoder.JSONDecodeError:
                    sdata[key] = value
        try:
            config_schema.validate({"nvtest": data})
        except SchemaError as e:
            raise ConfigSchemaError(file, e.args[0]) from None
        return data

    def dump(self, fh: TextIO):
        cfg = ConfigParser()
        for (section, data) in self.asdict().items():
            cfg.add_section(section)
            for (key, value) in data.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                cfg.set(section, key, str(value))
        cfg.write(fh)

    def load_user_config_file(self, config_file: Optional[str] = None) -> None:
        if config_file is None:
            config_file = self.find_user_config_file()
            if config_file is None:
                return None
        if not os.path.exists(config_file):
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), config_file
            )
        self.config.user_cfg_file = config_file
        cfg = self.loadcfg(config_file)
        for (section, section_data) in cfg.items():
            if section == "variables":
                for key, val in section_data.items():
                    val = Template(val).safe_substitute(os.environ)
                    self.variables[str(key)] = str(val)
            elif section == "config":
                for key, val in section_data.items():
                    setattr(self.config, key, val)
            elif section == "machine":
                for key, val in section_data.items():
                    setattr(self.machine, key, val)
        return None

    def set_main_options(self, args: argparse.Namespace) -> None:
        self.option = args
        user_log_level = tty.default_log_level() - args.q + args.v
        log_level = max(min(user_log_level, tty.max_log_level()), tty.min_log_level())
        tty.set_log_level(log_level)
        self.config.log_level = log_level
        self.config.debug = args.debug
        tty.set_debug(args.debug)
        for (var, val) in args.env_mods.items():
            self.variables[var] = val
        for path in args.config_mods:
            self.set(path)

    @property
    def debug(self) -> bool:
        return self.config.debug

    @property
    def log_level(self) -> int:
        return self.config.log_level

    @property
    def user_cfg_file(self):
        return self.config.user_cfg_file

    def asdict(self) -> dict:
        kwds = ns2dict(SimpleNamespace(**vars(self)))
        kwds.pop("option")
        return kwds

    def restore(self, **kwds):
        for var, val in kwds.get("variables", {}).items():
            self.variables[var] = val
        for key, val in kwds.get("config", {}).items():
            setattr(self.config, key, val)
        for var, val in kwds.get("machine", {}).items():
            if var in editable_machine_properties:
                setattr(self.machine, var, val)

    def set(self, path: str) -> None:
        parts = path.split(":")
        if parts and parts[0] == "machine":
            if len(parts) <= 1 or parts[1] not in editable_machine_properties:
                p = colorize("@*{%s}" % ":".join(parts[:-1]))
                raise ValueError(f"read-only machine property {p}")
        if parts and parts[0] not in self.sections:
            raise ValueError(f"invalid configuration {path!r}")
        elif parts and parts[0] not in self.editable_sections:
            raise ValueError(f"{path!r} is a read-only configuration")
        value = json.loads(parts.pop(-1))
        ns = self
        for i, part in enumerate(parts):
            if not hasattr(ns, part):
                p = ":".join(parts[:i])
                msg = f"Configuration path {p!r} has no attribute {part!r}"
                raise AttributeError(msg)
            if i == len(parts) - 1:
                break
            ns = getattr(ns, part)
        setattr(ns, part, value)

    def describe(self) -> str:
        import yaml

        return yaml.dump(self.asdict(), default_flow_style=False)


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
