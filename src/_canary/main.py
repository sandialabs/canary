# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import shlex
import signal
import sys
import traceback
from typing import TYPE_CHECKING
from typing import Sequence

from . import config
from .config.argparsing import make_argument_parser
from .error import StopExecution
from .third_party import color
from .third_party.monkeypatch import monkeypatch
from .util import logging

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
    if "CANARY_LEVEL" not in os.environ:
        os.environ["CANARY_LEVEL"] = "0"

    with CanaryMain(argv) as m:
        parser = make_argument_parser()
        parser.add_main_epilog(parser)
        for command in config.plugin_manager.get_subcommands():
            parser.add_command(command)
        with monkeypatch.context() as mp:
            mp.setattr(parser, "add_argument", parser.add_plugin_argument)
            mp.setattr(parser, "add_argument_group", parser.add_plugin_argument_group)
            config.plugin_manager.hook.canary_addoption(parser=parser)
        args = parser.parse_args(m.argv)
        if args.color:
            color.set_color_when(args.color)

        if args.echo:
            a = [os.path.join(sys.prefix, "bin/canary")] + [_ for _ in m.argv if _ != "--echo"]
            logging.emit(shlex.join(a) + "\n")
        config.set_main_options(args)
        config.plugin_manager.hook.canary_configure(config=config)
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
        self.argv: Sequence[str] = argv or sys.argv[1:]
        config.invocation_dir = config.working_dir = os.getcwd()

    def __enter__(self) -> "CanaryMain":
        """Preparsing is necessary to parse out options that need to take effect before the main
        program starts up"""
        global reraise
        if "GITLAB_CI" in os.environ:
            reraise = True
        parser = make_argument_parser()
        args = parser.preparse(self.argv)
        if args.debug:
            reraise = True
        if args.C:
            config.working_dir = args.C
        os.chdir(config.working_dir)
        for p in args.plugins:
            config.plugin_manager.consider_plugin(p)
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        os.chdir(config.invocation_dir)


class CanaryCommand:
    def __init__(self, command_name: str, debug: bool = False) -> None:
        # plugin.load_from_entry_points()
        for command in config.plugin_manager.get_subcommands():
            if command.name == command_name:
                self.command = command
                break
        else:
            raise ValueError(f"Unknown command {command_name!r}")
        self.debug = debug
        self.returncode = -1

    def __call__(self, *args_in: str, fail_on_error: bool = True) -> int:
        try:
            global reraise
            save_debug: bool | None = None
            save_reraise: bool | None = None
            if self.debug:
                save_debug = config.debug
                config.debug = True
                save_reraise = reraise
                reraise = True
            argv = [self.command.name] + list(args_in)
            parser = make_argument_parser()
            args = parser.preparse(argv, addopts=False)
            for p in args.plugins:
                config.plugin_manager.consider_plugin(p)
            for command in config.plugin_manager.get_subcommands():
                parser.add_command(command)
            with monkeypatch.context() as mp:
                mp.setattr(parser, "add_argument", parser.add_plugin_argument)
                mp.setattr(parser, "add_argument_group", parser.add_plugin_argument_group)
                config.plugin_manager.hook.canary_addoption(parser=parser)
            args = parser.parse_args(argv)
            config.set_main_options(args)
            rc = self.command.execute(args)
            self.returncode = rc
        except Exception:
            if fail_on_error:
                raise
            self.returncode = 1
        finally:
            if save_debug is not None:
                config.debug = save_debug
            if save_reraise is not None:
                reraise = save_reraise
        return self.returncode


def invoke_command(command: "CanarySubcommand", args: argparse.Namespace) -> int:
    return command.execute(args)


class Profiler:
    def __init__(self, nlines: int = -1):
        self.nlines = nlines
        try:
            import pyinstrument

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
            self.profiler.print()
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


def console_main() -> int:
    """The CLI entry point of canary.

    This function is not meant for programmable use; use `main()` instead.
    """
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
            logging.info(e.message)
        else:
            logging.error(e.message)
        return e.exit_code
    except TimeoutError as e:
        if reraise:
            raise
        logging.error(e.args[0])
        return 4
    except KeyboardInterrupt:
        if reraise:
            raise
        sys.stderr.write("\n")
        logging.error("Keyboard interrupt.")
        return signal.SIGINT.value
    except SystemExit as e:
        if e.code == 0:
            return 0
        if reraise:
            traceback.print_exc()
        if isinstance(e.code, int):
            return e.code
        return 1
    except Exception as e:
        if reraise:
            raise
        logging.error(str(e))
        return 3
