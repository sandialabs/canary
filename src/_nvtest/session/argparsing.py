import argparse
import inspect
import re
import textwrap as textwrap
from typing import Optional
from typing import Type

from ..util import tty


class HelpFormatter(argparse.RawTextHelpFormatter):
    def _split_lines(self, text, width):
        text = self._whitespace_matcher.sub(" ", text).strip()
        _, cols = tty.terminal_size()
        return textwrap.wrap(text, int(2 * cols / 3.0))

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


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register("type", None, identity)
        self.__subcommands: dict[str, Type] = {}

    @staticmethod
    def _validate_command_class(cmdclass: Type):
        def _defines_method(cls, method_name):
            method = getattr(cls, method_name, None)
            return callable(method)

        if not inspect.isclass(cmdclass):
            raise TypeError("nvtest.plugins.command must wrap classes")

        for method in ("add_options", "setup", "run", "teardown"):
            if not _defines_method(cmdclass, method):
                raise AttributeError(
                    f"{cmdclass.__name__} must define a {method} method"
                )

        for attr in ("description",):
            if not hasattr(cmdclass, attr):
                raise AttributeError(
                    f"{cmdclass.__name__} must define a {attr} attribute"
                )

        if not hasattr(cmdclass, "name"):
            cmdclass.name = cmdclass.__name__.lower()

    def add_command(self, cmdclass: Type) -> None:
        """Add one subcommand to this parser."""
        # lazily initialize any subparsers
        if not hasattr(self, "subparsers"):
            # remove the dummy "command" argument.
            if self._actions[-1].dest == "command":
                self._remove_action(self._actions[-1])
            self.subparsers = self.add_subparsers(metavar="subcommands", dest="command")

        self._validate_command_class(cmdclass)

        subparser = self.subparsers.add_parser(
            cmdclass.name,
            aliases=getattr(cmdclass, "aliases", None) or [],
            help=getattr(cmdclass, "description", None),
            description=getattr(cmdclass, "description", None),
            epilog=getattr(cmdclass, "epilog", None),
            add_help=getattr(cmdclass, "add_help", False),
        )
        subparser.register("type", None, identity)
        cmdclass.add_options(subparser)  # type: ignore
        self.__subcommands[cmdclass.name] = cmdclass

    def get_command(self, cmdname: str) -> Optional[Type]:
        for (name, cmdclass) in self.__subcommands.items():
            if name == cmdname:
                return cmdclass
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


class EnvironmentModification:
    def __init__(self, arg: str) -> None:
        var, val = [_.strip() for _ in arg.split("=", 1)]
        try:
            var, val = [_.strip() for _ in arg.split("=", 1)]
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid environment variable {arg!r} specification. "
                "Expected form NAME=VAL"
            ) from None
        else:
            self.var = var
            self.val = val


def make_argument_parser(**kwargs):
    """Create an basic argument parser without any subcommands added."""
    parser = ArgumentParser(
        formatter_class=HelpFormatter,
        description="nv.test - an application testing framework",
        prog="nv.test",
        **kwargs,
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "-v",
        default=0,
        action="count",
        help="Increase console logging level by 1",
    )
    g.add_argument(
        "-q",
        default=0,
        action="count",
        help="Decrease console logging level by 1",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Debug mode [default: %(default)s]",
    )
    parser.add_argument(
        "-t",
        "--timeit",
        action="store_true",
        default=False,
        help="Time execution of command [default: %(default)s]",
    )
    parser.add_argument(
        "-C",
        "--config-file",
        dest="config_file",
        metavar="CONFIG",
        help="Path to alternative configuration file",
    )
    parser.add_argument(
        "--no-user-config",
        action="store_true",
        default=False,
        help="Do not load a user configuration file",
    )
    parser.add_argument(
        "-c",
        dest="config_mods",
        action="append",
        metavar="PATH",
        default=[],
        help="Colon-separated path to config that should be "
        "added to the testing environment, e.g. 'config:debug:true'",
    )
    parser.add_argument(
        "-w",
        dest="wipe",
        action="store_true",
        help="Remove test execution directory, if it exists [default: %(default)s]",
    )
    parser.add_argument(
        "-d",
        "--work-dir",
        dest="workdir",
        default=None,
        help="Root path to test work (execution) directory [default: ./TestResults]",
    )
    parser.add_argument(
        "-e",
        dest="env_mods",
        action="append",
        metavar="ENVAR",
        default=[],
        type=EnvironmentModification,
        help="Environment variables that should be added to "
        "the testing environment, e.g. 'NAME=VAL'",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="1.0",
        help="show version and exit",
    )

    return parser
