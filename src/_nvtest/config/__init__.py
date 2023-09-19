import argparse
import copy
import dataclasses
import errno
import json
import os
import sys
from string import Template
from types import SimpleNamespace
from typing import Any
from typing import Iterable
from typing import Optional
from typing import Union
from typing import final

import toml

from .. import plugin
from ..schemas import config_schema
from ..util import tty
from ..util.misc import ns2dict
from ..util.schema import SchemaError
from ..util.tty.color import colorize
from .argparsing import make_argument_parser
from .machine import editable_properties as editable_machine_properties
from .machine import machine_config

user_config_filename = "nvtest.toml"


def setdefault(namespace: argparse.Namespace, attr: str, default: Any) -> Any:
    try:
        return getattr(namespace, attr)
    except AttributeError:
        setattr(namespace, attr, default)
        return default


class Config:
    """Access to configuration values"""

    @final
    @dataclasses.dataclass(frozen=True)
    class InvocationParams:
        """Holds parameters passed during :func:`nvtest.main`.

        The object attributes are read-only.

        """

        args: tuple[str, ...]
        dir: str  # The directory from which :func:`nvtest.main` was invoked

        def __init__(self, *, args: Iterable[str], dir: str) -> None:
            object.__setattr__(self, "args", tuple(args))
            object.__setattr__(self, "dir", dir)

    sections = ("config", "machine", "variables", "python")
    editable_sections = ("config", "machine", "variables")

    def __init__(self, *, invocation_params: InvocationParams):
        self.invocation_params = invocation_params
        self.orig_invocation_params = invocation_params
        self.config = SimpleNamespace(debug=False, log_level=2, user_cfg_file=None)
        self.machine = machine_config()
        self.variables: dict[str, str] = {}
        self.python = SimpleNamespace(
            executable=sys.executable,
            version=".".join(str(_) for _ in sys.version_info[:3]),
            version_info=list(sys.version_info),
        )
        self.dir = self.invocation_params.dir
        self.parser = make_argument_parser()
        self.option = argparse.Namespace()
        self.load_user_config_file()
        ns, remaining = self.parser.preparse(
            self.invocation_params.args, namespace=copy.copy(self.option)
        )
        self.set_main_options(ns)
        self.load_plugins()
        group = self.parser.get_group("plugin options")
        for hook in plugin.plugins("argparse", "add_argument"):
            hook(self, group)
        for hook in plugin.plugins("argparse", "add_command"):
            hook(self, self.parser)
        if remaining and remaining[0] != "-":
            self.set_subcommand_defaults(remaining[0])
        self.parser.parse_args(self.invocation_params.args, namespace=self.option)

    @property
    def debug(self) -> bool:
        return self.config.debug

    @debug.setter
    def debug(self, arg):
        self.config.debug = bool(arg)
        if self.config.debug:
            os.environ["NVTEST_CONFIG_DEBUG"] = "1"
        else:
            os.environ.pop("NVTEST_CONFIG_DEBUG", None)

    @property
    def log_level(self) -> int:
        return self.config.log_level

    @log_level.setter
    def log_level(self, log_level: int):
        self.config.log_level = log_level

    @property
    def user_cfg_file(self):
        return self.config.user_cfg_file

    @user_cfg_file.setter
    def user_cfg_file(self, arg):
        self.config.user_cfg_file = arg

    def asdict(self) -> dict:
        kwds = ns2dict(SimpleNamespace(**vars(self)))
        kwds["invocation_params"] = ns2dict(kwds.pop("invocation_params"))
        kwds.pop("parser")
        kwds.pop("option")
        kwds.pop("orig_invocation_params", None)
        return kwds

    def set_subcommand_defaults(self, subcommand: str) -> None:
        opts = getattr(self.option, "__subopts__", {})
        kwds = opts.get(subcommand)
        if not kwds:
            return
        for (name, parser) in self.parser.subparsers.choices.items():
            if name == subcommand:
                parser.set_defaults(**kwds)

    def set_main_options(self, args: argparse.Namespace) -> None:
        user_log_level = tty.default_log_level() - args.q + args.v
        log_level = max(min(user_log_level, tty.max_log_level()), tty.min_log_level())
        tty.set_log_level(log_level)
        self.log_level = log_level
        self.debug = args.debug
        for (var, val) in args.env_mods.items():
            self.variables[var] = val
        for path in args.config_mods:
            self.set(path)

    def find_user_config_file(self) -> Union[str, None]:
        cwd = os.getcwd()
        f: str = user_config_filename
        home = os.path.expanduser("~")
        opts, _ = self.parser.preparse(self.invocation_params.args)
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

    def load_user_config_file(self, config_file: Optional[str] = None) -> None:
        if config_file is None:
            config_file = self.find_user_config_file()
            if config_file is None:
                return None
        if not os.path.exists(config_file):
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), config_file
            )
        self.user_cfg_file = config_file
        cfg = toml.load(config_file)
        try:
            config_schema.validate(cfg)
        except SchemaError as e:
            raise ConfigSchemaError(config_file, e.args[0]) from None
        for (section, section_data) in cfg.get("nvtest", {}).items():
            if section == "variables":
                env_mods = setdefault(self.option, "env_mods", {})
                for key, val in section_data.items():
                    val = Template(val).safe_substitute(os.environ)
                    env_mods[key] = val
            elif section == "config":
                config_mods = setdefault(self.option, "config_mods", [])
                for key, val in section_data.items():
                    if key == "debug":
                        val = str(val).lower()
                    config_mods.append(f"config:{key}:{val}")
            elif section == "machine":
                config_mods = setdefault(self.option, "config_mods", [])
                for key, val in section_data.items():
                    config_mods.append(f"machine:{key}:{val}")
            else:
                opts = setdefault(self.option, "__subopts__", {})
                opts[section] = section_data
        return None

    @staticmethod
    def load_plugins() -> None:
        import _nvtest.plugins

        path = _nvtest.plugins.__path__
        namespace = _nvtest.plugins.__name__
        plugin.load(path, namespace)

    def restore(self, **kwds):
        for var, val in kwds.get("variables", {}).items():
            self.variables[var] = val
        for key, val in kwds.get("config", {}).items():
            setattr(self.config, key, val)
        for var, val in kwds.get("machine", {}).items():
            if var in editable_machine_properties:
                setattr(self.machine, var, val)
        ipd: dict[str, Any] = kwds["invocation_params"]
        ip = self.InvocationParams(args=tuple(ipd["args"]), dir=ipd["dir"])
        self.orig_invocation_params = ip

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
