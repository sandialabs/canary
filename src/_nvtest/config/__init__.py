import dataclasses
import errno
import json
import os
import sys
from configparser import ConfigParser
from string import Template
from types import SimpleNamespace
from typing import Any
from typing import Iterable
from typing import Optional
from typing import Union
from typing import final

from .. import plugin
from ..util import tty
from ..util.misc import ns2dict
from ..util.tty.color import colorize
from .argparsing import make_argument_parser
from .machine import editable_properties as editable_machine_properties
from .machine import machine_config

user_config_filename = "nvtest.ini"


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
        self.config = SimpleNamespace(
            debug=False, log_level=2, user_cfg_file=None, disable_user_config=False
        )
        self.machine = machine_config()
        self.variables: dict[str, str] = {}
        self.python = SimpleNamespace(
            executable=sys.executable,
            version=".".join(str(_) for _ in sys.version_info[:3]),
            version_info=list(sys.version_info),
        )
        self.dir = self.invocation_params.dir
        self.parser = make_argument_parser()
        self.load_plugins()
        for hook in plugin.plugins("argparse", "add_command"):
            hook(self, self.parser)
        group = self.parser.get_group("plugin options")
        for hook in plugin.plugins("argparse", "add_argument"):
            hook(self, group)
        self.option = self.parser.parse_args(self.invocation_params.args)
        self.set_main_options()
        self.load_user_config_file()

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

    def set_main_options(self) -> None:
        args = self.option
        user_log_level = tty.default_log_level() - args.q + args.v
        log_level = max(min(user_log_level, tty.max_log_level()), tty.min_log_level())
        tty.set_log_level(log_level)
        self.log_level = log_level
        self.debug = args.debug
        for env in args.env_mods:
            self.variables[env.var] = env.val
        for path in args.config_mods:
            self.set(path)
        if args.config_file == "none":
            self.config.disable_user_config = True
        elif args.config_file:
            self.user_cfg_file = args.config_file

    def find_user_config_file(self) -> Union[str, None]:
        cwd = os.getcwd()
        f: str = user_config_filename
        home = os.path.expanduser("~")
        if os.path.exists(os.path.join(cwd, ".nvtest", f)):
            return os.path.join(cwd, ".nvtest", f)
        elif os.path.exists(os.path.join(cwd, f)):
            return os.path.join(cwd, f)
        elif os.path.exists(os.path.join(home, ".config", f)):
            return os.path.join(home, ".config", f)
        elif os.path.exists(os.path.join(home, "." + f)):
            return os.path.join(home, "." + f)
        return None

    def load_user_config_file(self, config_file: Optional[str] = None) -> None:
        class RawConfigParser(ConfigParser):
            def optionxform(self, option):
                return option

            def items(self, section, *args, **kwargs):
                kwargs["raw"] = True
                return super(RawConfigParser, self).items(section, *args, **kwargs)

        if self.config.disable_user_config:
            return None
        if config_file is None:
            config_file = self.find_user_config_file()
            if config_file is None:
                return
        if not os.path.exists(config_file):
            raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), config_file
            )
        self.user_cfg_file = config_file
        cfg = RawConfigParser()
        cfg.read(config_file)
        for section in cfg.sections():
            if section == "variables":
                for key, val in cfg.items("variables"):
                    t = Template(val)
                    self.variables[key] = t.safe_substitute(os.environ)
            elif section == "config":
                for key, val in cfg.items("config"):
                    if key not in vars(self.config):
                        raise ValueError(f"Illegal configuration setting: config:{key}")
                    if key == "debug":
                        val = str2bool(val)
                    elif key == "log_level":
                        val = int(val)
                    setattr(self.config, key, val)
            elif section == "machine":
                for key, val in cfg.items("machine"):
                    if key not in editable_machine_properties:
                        raise ValueError(f"machine:{key} is a read only property")
                    prop_type = type(getattr(self.machine, key))
                    setattr(self.machine, key, prop_type(val))
            else:
                errmsg = f"Illegal configuration section {section} in {config_file}"
                raise ValueError(errmsg)

    @staticmethod
    def load_plugins() -> None:
        import _nvtest.plugins

        path = _nvtest.plugins.__path__
        namespace = _nvtest.plugins.__name__
        plugin.load(path, namespace)

    def restore(self, kwds: dict[str, Any]):
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
        self.set_main_options()

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


def str2bool(arg: str):
    return False if arg.lower() in ("0", "no", "false", "off") else True
