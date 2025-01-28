import argparse
import json
import pstats
import re
import shlex
import sys
import textwrap as textwrap
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

from .. import version
from ..third_party.color import colorize
from ..util.collections import merge
from ..util.term import terminal_size

if TYPE_CHECKING:
    from ..plugins.types import CanarySubcommand

stat_names = pstats.Stats.sort_arg_dict_default


class HelpFormatter(argparse.RawTextHelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._indent_increment = 2

    def _split_lines(self, text, width):
        """Help messages can add new lines by including \n\n"""
        _, cols = terminal_size()
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


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        positionals_title = kwargs.pop("positionals_title", None)
        super().__init__(*args, **kwargs)
        self.register("type", None, identity)
        self.__subcommand_objects: dict[str, "CanarySubcommand"] = {}
        self.__subcommand_parsers: dict[str, "Parser"] = {}
        self.argv: Sequence[str] = sys.argv[1:]
        if positionals_title:
            self._positionals.title = positionals_title

    def convert_arg_line_to_args(self, arg_line: str) -> list[str]:
        return shlex.split(arg_line.split("#", 1)[0].strip())

    def preparse(self, args: list[str]):
        known_commands = [
            "run",
            "report",
            "log",
            "location",
            "info",
            "help",
            "find",
            "fetch",
            "describe",
            "config",
        ]
        ns = argparse.Namespace(plugin_dirs=[], debug=False, C=None)
        i = 0
        n = len(args)
        while i < n:
            opt = args[i]
            i += 1
            if opt in known_commands:
                return ns
            if isinstance(opt, str):
                if opt == "-p":
                    try:
                        ns.plugin_dirs.append(args[i].strip())
                    except IndexError:
                        return ns
                    i += 1
                elif opt.startswith("-p"):
                    ns.plugin_dirs.append(opt[2:].strip())
                elif opt in ("-d", "--debug"):
                    ns.debug = True
                elif opt == "-C":
                    try:
                        ns.C = args[i]
                    except IndexError:
                        return ns
                    i += 1
                elif opt.startswith("-C"):
                    ns.C = opt[2:]
                else:
                    continue
        return ns

    def parse_known_args(self, args=None, namespace=None):
        if args is not None:
            self.argv = args
        namespace, unknown_args = super().parse_known_args(args, namespace)
        return namespace, unknown_args

    def _read_args_from_files(self, arg_strings: list[str]) -> list[str]:
        arg_strings = super()._read_args_from_files(arg_strings)
        self.argv = arg_strings
        return arg_strings

    def add_command(self, command: "CanarySubcommand", add_help_override: bool = False) -> None:
        """Add one subcommand to this parser."""
        # lazily initialize any subparsers
        if not hasattr(self, "subparsers"):
            # remove the dummy "command" argument.
            if self._actions[-1].dest == "command":
                self._remove_action(self._actions[-1])
            self.subparsers = self.add_subparsers(metavar="", dest="command")
        kwds: dict[str, Any] = dict(
            description=command.description,
            formatter_class=HelpFormatter,
        )
        if command.add_help or add_help_override:
            kwds["add_help"] = False
            kwds["epilog"] = command.epilog
            kwds["help"] = command.description
        subparser = self.subparsers.add_parser(command.name, **kwds)
        subparser.register("type", None, identity)
        if command.setup_parser:
            command.setup_parser(subparser)  # type: ignore
        try:
            add_parser_help(subparser)
        except argparse.ArgumentError:
            pass

        self.__subcommand_objects[command.name] = command
        self.__subcommand_parsers[command.name] = subparser

    def get_command(self, cmdname: str) -> "CanarySubcommand | None":
        for name, command in self.__subcommand_objects.items():
            if cmdname == name:
                return command
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
        parser = self.__subcommand_parsers.get(kwargs.pop("command", None)) or self
        group_name = "plugin options"
        for group in parser._action_groups:
            if group.title == group_name:
                break
        else:
            group = parser.add_argument_group(group_name)
        group.add_argument(*args, **kwargs)


def identity(arg):
    return arg


class EnvironmentModification(argparse.Action):
    def __init__(self, option_strings, dest, default_scope="session", **kwargs):
        self.default_scope = default_scope
        super().__init__(option_strings, dest, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        option: str | Sequence[Any] | None,
        option_str: str | None = None,
    ):
        assert isinstance(option, str)
        try:
            var, val = [_.strip() for _ in option.split("=", 1)]
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid environment variable {option!r} specification. Expected form NAME=VAL"
            ) from None
        scope = self.default_scope
        if ":" in var:
            scope, var = var.split(":", 1)
        env_mods: dict[str, dict[str, str]] = getattr(namespace, self.dest, None) or {}
        env_mods.setdefault(scope, {})[var] = val
        setattr(namespace, self.dest, env_mods)


class ConfigMods(argparse.Action):
    def __call__(self, parser, namespace, option, option_str=None):
        *parts, value = option.split(":")
        data = {}
        current = data
        while len(parts) > 1:
            key = parts.pop(0)
            current[key] = {}
            current = current[key]
        current[parts[0]] = safe_loads(value)
        config = getattr(namespace, self.dest, None) or {}
        config = merge(config, data)
        setattr(namespace, self.dest, config)


def make_argument_parser(**kwargs):
    """Create an basic argument parser without any subcommands added."""
    parser = Parser(
        formatter_class=HelpFormatter,
        description="canary - an application testing framework",
        fromfile_prefix_chars="@",
        prog="canary",
        positionals_title="subcommands",
        **kwargs,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=version.version,
        help="show version and exit",
    )
    parser.add_argument(
        "-C",
        default=None,
        metavar="path",
        help=colorize(
            "Run as if canary was started in @*{path} instead of the current working directory."
        ),
    )
    parser.add_argument(
        "-p",
        default=None,
        dest="plugin_dirs",
        action="append",
        metavar="directory",
        help="Search directories for canary plugins.",
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
    parser.add_argument(
        "--echo",
        action="store_true",
        default=False,
        help="Echo command line to the console [default: %(default)s]",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default=None,
        help="When to color output [default: auto]",
    )
    group = parser.add_argument_group("profiling")
    group.add_argument(
        "--profile",
        action="store_true",
        dest="canary_profile",
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
        help="lines of profile output or 'all' [default: 20]",
    )
    group = parser.add_argument_group("runtime configuration")
    group.add_argument(
        "-f",
        dest="config_file",
        metavar="file",
        help="Read local configuration settings from this file",
    )
    group.add_argument(
        "-c",
        dest="config_mods",
        action=ConfigMods,
        metavar="path",
        help="Add the colon-separated path to test session's configuration, "
        "e.g. %s" % colorize("@*{-c config:debug:true}"),
    )
    group.add_argument(
        "-e",
        dest="env_mods",
        metavar="var=val",
        default={},
        action=EnvironmentModification,
        default_scope="session",
        help="Add environment variable %s to the testing environment with value %s.  Accepts "
        "optional scope using the form %s:var=val.  Valid scopes are: "
        "session: set environment variable for whole session; "
        "test: set environment variable only during test execution"
        % (colorize("@*{var}"), colorize("@*{val}"), colorize("@*{scope}")),
    )

    return parser


def safe_loads(arg):
    try:
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


def add_parser_help(p: argparse.ArgumentParser) -> None:
    """
    So we can use consistent capitalization and periods in the help. You must
    use the add_help=False argument to ArgumentParser or add_parser to use
    this. Add this first to be consistent with the default argparse output.

    """
    p.add_argument(
        "-h",
        "--help",
        action=argparse._HelpAction,
        help="Show this help message and exit.",
    )
