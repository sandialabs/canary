import argparse
import inspect
import pstats
import re
import shlex
import sys
import textwrap as textwrap
from types import ModuleType
from typing import Any
from typing import Optional
from typing import Sequence
from typing import Type
from typing import Union

import _nvtest._version
from ..util import tty
from ..util.tty.color import colorize

stat_names = pstats.Stats.sort_arg_dict_default


class HelpFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._indent_increment = 2

    def _split_lines(self, text, width):
        """Help messages can add new lines by including \n\n"""
        _, cols = tty.terminal_size()
        width = int(2.0 * cols / 3.0)
        lines = []
        for line in text.split("\n\n"):
            line = self._whitespace_matcher.sub(" ", line).strip()
            wrapped = textwrap.wrap(line, width)
            lines.extend(wrapped or ["\n"])
        return lines

    def _format_actions_usage(self, actions, groups):
        """Formatter with more concise usage strings."""
        usage = super(HelpFormatter, self)._format_actions_usage(actions, groups)

        # compress single-character flags that are not mutually exclusive
        # at the beginning of the usage string
        chars = "".join(re.findall(r"\[-(.)\]", usage))
        usage = re.sub(r"\[-.\] ?", "", usage)
        if chars:
            return "[-%s] %s" % (chars, usage)
        else:
            return usage

    def _iter_indented_subactions(self, action):
        try:
            get_subactions = action._get_subactions
        except AttributeError:
            pass
        else:
            yield from get_subactions()


def cmd_name(module: ModuleType) -> str:
    return module.__name__.lower().split(".")[-1].replace("_", "-")


def py_name(module: ModuleType) -> str:
    return module.__name__.lower().split(".")[-1]


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.register("type", None, identity)
        self.__subcommand_modules: dict[str, ModuleType] = {}
        self.argv: Sequence[str] = sys.argv[1:]

    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:
        return shlex.split(arg_line.split("#", 1)[0].strip())

    def preparse(self, args: Optional[list[str]] = None, namespace=None):
        argv: list[str] = sys.argv[1:] if args is None else args
        args = [_ for _ in argv if _ not in ("-h", "--help")]
        return super().parse_known_args(args, namespace=namespace)[0]

    @staticmethod
    def _validate_command_module(module: ModuleType):
        def _defines_method(module, method_name):
            method = getattr(module, method_name, None)
            return callable(method)

        name: str = module.__name__
        if not inspect.ismodule(module):
            raise TypeError(f"{module} is not a module")

        for method in ("setup_parser", py_name(module)):
            if not _defines_method(module, method):
                raise AttributeError(f"{name} must define a {method} method")

        for attr in ("description",):
            if not hasattr(module, attr):
                raise AttributeError(f"{name} must define a {attr} attribute")

        if hasattr(module, "aliases") and not isinstance(module.aliases, list):
            a_type = type(module.aliases).__name__
            raise TypeError(f"{name}.aliases must be a list, not {a_type}")

    def parse_known_args(self, args=None, namespace=None):
        if args is not None:
            self.argv = args
        return super().parse_known_args(args, namespace)

    def _read_args_from_files(self, arg_strings: list[str]) -> list[str]:
        arg_strings = super()._read_args_from_files(arg_strings)
        self.argv = arg_strings
        return arg_strings

    def add_command(self, module: ModuleType) -> None:
        """Add one subcommand to this parser."""
        # lazily initialize any subparsers
        if not hasattr(self, "subparsers"):
            # remove the dummy "command" argument.
            if self._actions[-1].dest == "command":
                self._remove_action(self._actions[-1])
            self.subparsers = self.add_subparsers(metavar="", dest="command")
        self._validate_command_module(module)
        cmdname = cmd_name(module)
        subparser = self.subparsers.add_parser(
            cmdname,
            aliases=getattr(module, "aliases", None) or [],
            help=module.description,
            description=module.description,
            epilog=getattr(module, "epilog", None),
            add_help=getattr(module, "add_help", True),
            formatter_class=HelpFormatter,
        )
        subparser.register("type", None, identity)
        module.setup_parser(subparser)  # type: ignore
        self.__subcommand_modules[cmdname] = module

    def get_command(self, cmdname: str) -> Optional[Type]:
        for name, module in self.__subcommand_modules.items():
            candidates = [name] + getattr(module, "aliases", [])
            if cmdname in candidates:
                return getattr(module, py_name(module))
        return None

    def remove_argument(self, opt_string):
        for action in self._actions:
            opts = action.option_strings
            if (opts and opts[0] == opt_string) or action.dest == opt_string:
                self._remove_action(action)
                break

        for action in self._action_groups:
            for group_action in action._group_actions:
                opts = group_action.option_strings
                if (opts and opts[0] == opt_string) or group_action.dest == opt_string:
                    action._group_actions.remove(group_action)
                    return

    def get_group(self, group_name: str):
        for group in self._action_groups:
            if group.title == group_name:
                break
        else:
            group = self.add_argument_group(group_name)
        return group

    def add_plugin_argument(self, *args, **kwargs):
        group = self.get_group("plugin options")
        group.add_argument(*args, **kwargs)


def identity(arg):
    return arg


class EnvironmentModification(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: Union[str, Sequence[Any], None],
        option_str: Optional[str] = None,
    ):
        assert isinstance(option, str)
        try:
            var, val = [_.strip() for _ in option.split("=", 1)]
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid environment variable {option!r} specification. "
                "Expected form NAME=VAL"
            ) from None
        env_mods: dict[str, str] = getattr(namespace, self.dest, None) or {}
        env_mods[var] = val
        setattr(namespace, self.dest, env_mods)


def make_argument_parser(**kwargs):
    """Create an basic argument parser without any subcommands added."""
    parser = Parser(
        formatter_class=HelpFormatter,
        description="nvtest - an application testing framework",
        fromfile_prefix_chars="@",
        prog="nvtest",
        **kwargs,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=_nvtest._version.version,
        help="show version and exit",
    )
    parser.add_argument(
        "-C",
        default=None,
        metavar="path",
        help="Run as if nvtest was started in path "
        "instead of the current working directory.",
    )
    parser.add_argument(
        "-P",
        default=None,
        dest="plugin_dirs",
        action="append",
        metavar="directory",
        help="Search directories for nvtest plugins.",
    )
    group = parser.add_argument_group("console reporting")
    group.add_argument(
        "-v",
        default=0,
        action="count",
        help="Increase console logging level by 1",
    )
    group.add_argument(
        "-q",
        default=0,
        action="count",
        help="Decrease console logging level by 1",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Debug mode [default: %(default)s]",
    )
    group = parser.add_argument_group("profiling")
    group.add_argument(
        "--profile",
        action="store_true",
        dest="nvtest_profile",
        help="profile execution using cProfile",
    )
    stat_lines = list(zip(*(iter(stat_names),) * 7))
    group.add_argument(
        "--sorted-profile",
        default=None,
        metavar="stat",
        help="profile and sort by one or more of:\n[%s]"
        % ",\n ".join([", ".join(line) for line in stat_lines]),
    )
    group.add_argument(
        "--lines",
        default=20,
        action="store",
        help="lines of profile output or 'all' (default: 20)",
    )
    group = parser.add_argument_group("runtime configuration")
    group.add_argument(
        "-c",
        dest="config_mods",
        action="append",
        metavar="path",
        default=[],
        help="Add the colon-separated path to test session's configuration, "
        "e.g. %s" % colorize("@*{-c config:debug:true}"),
    )
    group.add_argument(
        "-e",
        dest="env_mods",
        metavar="var=val",
        default={},
        action=EnvironmentModification,
        help="Add environment variable %s to the testing environment with value %s"
        % (colorize("@*{var}"), colorize("@*{val}")),
    )

    return parser
