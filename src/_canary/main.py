# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import shlex
import signal
import sys
import traceback
import urllib.parse
from typing import TYPE_CHECKING
from typing import Any
from typing import Sequence

import yaml

from . import config
from .config.argparsing import make_argument_parser
from .error import StopExecution
from .third_party import color
from .util import logging
from .util.collections import contains_any

if TYPE_CHECKING:
    from .plugins.types import CanarySubcommand


reraise: bool = False


def main(argv: Sequence[str] | None = None) -> int:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).

    :returns: An exit code.
    """
    with CanaryMain(argv) as m:
        parser = make_argument_parser()
        parser.add_main_epilog(parser)
        config.pluginmanager.hook.canary_addhooks(pluginmanager=config.pluginmanager)
        config.pluginmanager.hook.canary_addcommand(parser=parser)
        config.pluginmanager.hook.canary_addoption(parser=parser)
        args = parser.parse_args(m.argv)
        if args.echo:
            a = [os.path.join(sys.prefix, "bin/canary")] + [_ for _ in m.argv if _ != "--echo"]
            sys.stderr.write(shlex.join(a) + "\n")
        if args.color:
            color.set_color_when(args.color)
        config.set_main_options(args)
        config.pluginmanager.hook.canary_configure(config=config)
        command = parser.get_command(args.command)
        if command is None:
            parser.print_help()
            return -1
        if args.canary_profile:
            return invoke_profiled_command(command, args)
        else:
            return invoke_command(command, args)


class CanaryMain:
    """Set up and teardown this canary session"""

    def __init__(self, argv: Sequence[str] | None = None) -> None:
        self.argv: Sequence[str] = list(argv or sys.argv[1:])
        config.invocation_dir = config.working_dir = os.getcwd()

    def __enter__(self) -> "CanaryMain":
        """Preparsing is necessary to parse out options that need to take effect before the main
        program starts up"""
        global reraise
        if contains_any(os.environ.keys(), "CANARY_RERAISE_ERRORS", "GITLAB_CI"):
            reraise = True
        parser = make_argument_parser()
        args = parser.preparse(self.argv, addopts=True)
        if args.debug:
            reraise = True
        if args.C:
            config.working_dir = args.C
        os.chdir(config.working_dir)

        # Consider plugins passed in the environment and the command line early, before parsing the
        # main command line. This allows plugins to define a subcommand (which must be registered
        # before it can be run)
        for p in args.plugins:
            config.pluginmanager.consider_plugin(p)
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        os.chdir(config.invocation_dir)


def invoke_command(command: "CanarySubcommand", args: argparse.Namespace) -> int:
    return command.execute(args)


class Profiler:
    def __init__(self, nlines: int = -1):
        self.nlines = nlines
        try:
            import pyinstrument  # ty: ignore[unresolved-import]

            self.profiler = pyinstrument.Profiler()  # type: ignore
            self.type = 1
        except ImportError:
            import cProfile

            self.profiler = cProfile.Profile()  # type: ignore
            self.type = 2

    def __enter__(self):
        if self.type == 1:
            self.profiler.start()
        else:
            self.profiler.enable()

    def __exit__(self, *args):
        if self.type == 1:
            self.profiler.stop()
            self.profiler.print(show_all=True)
        else:
            import pstats

            self.profiler.disable()
            stats = pstats.Stats(self.profiler)
            stats.print_stats(self.nlines)


def invoke_profiled_command(command, args):
    try:
        nlines = int(args.profiling_lines or 20)
    except ValueError:
        if args.profiling_lines != "all":
            raise ValueError("Invalid number for --lines: %s" % args.profiling_lines)
        nlines = -1

    with Profiler(nlines=nlines):
        rc = invoke_command(command, args)
    return rc


def determine_plugin_from_tb(tb: traceback.StackSummary) -> None | Any:
    """Determine if the exception was raised inside a plugin"""

    def filename(obj):
        import inspect

        if f := getattr(obj, "__file__", None):
            return f
        return inspect.getfile(obj.__class__)

    for frame in tb[::-1]:
        # Check if the frame corresponds to a registered plugin
        for plugin in config.pluginmanager.get_plugins():
            if plugin and frame.filename == filename(plugin):
                return plugin
    return None


def print_current_config() -> None:
    state = config.getstate(pretty=True)
    text = yaml.dump(state, default_flow_style=False)
    print("Current canary configuration:")
    print(text)


def console_main() -> int:
    """The CLI entry point of canary.

    This function is not meant for programmable use; use `main()` instead.
    """

    # Some CI/CD agents use yaml to describe jobs.  Quoting can get wonky between parsing the
    # yaml and passing it to the shell.  So, we allow url encoded strings and unquote them
    # here.
    logger = logging.get_logger(__name__)
    for i, arg in enumerate(sys.argv):
        sys.argv[i] = urllib.parse.unquote(arg)
    try:
        returncode = main()
        sys.stdout.flush()
        return returncode
    except BrokenPipeError:
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1  # Python exits with error code 1 on EPIPE
    except StopExecution as e:
        if e.exit_code == 0:
            logger.info(e.message)
        else:
            logger.error(e.message)
        return e.exit_code
    except TimeoutError as e:
        if reraise:
            raise
        if config.get("config:debug"):
            print_current_config()
        logger.error(e.args[0])
        return 4
    except KeyboardInterrupt:
        if reraise:
            raise
        sys.stderr.write("\n")
        logger.error("Keyboard interrupt.")
        return signal.SIGINT.value
    except SystemExit as e:
        if e.code == 0:
            return 0
        if config.get("config:debug"):
            print_current_config()
        if reraise:
            traceback.print_exc()
        if isinstance(e.code, int):
            return e.code
        return 1
    except Exception as e:
        if config.get("config:debug"):
            print_current_config()
        if reraise:
            raise
        tb = traceback.extract_tb(e.__traceback__)
        err = str(e)
        if plugin := determine_plugin_from_tb(tb):
            err += f" (from plugin: {plugin})"
        logger.error(err)
        return 3
