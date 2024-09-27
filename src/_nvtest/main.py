import argparse
import os
import shlex
import signal
import sys
import traceback
from types import FunctionType
from typing import Optional

from . import command as cmd
from . import config
from . import plugin
from .config.argparsing import make_argument_parser
from .error import StopExecution
from .util import logging


def main(argv: Optional[list[str]] = None) -> int:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).

    :returns: An exit code.
    """
    parser = make_argument_parser()

    if "NVTEST_LEVEL" not in os.environ:
        os.environ["NVTEST_LEVEL"] = "0"

    argv = argv or sys.argv[1:]

    try:
        pre = parser.preparse(argv)
        os.chdir(pre.C or config.invocation_dir)
        config.set_main_options(pre)
        if pre.echo:
            a = [os.path.join(sys.prefix, "bin/nvtest")] + [_ for _ in argv if _ != "--echo"]
            logging.emit(shlex.join(a) + "\n")

        load_plugins(pre.plugin_dirs or [])
        for hook in plugin.plugins("main", "setup"):
            hook(parser)

        cmd.add_all_commands(parser)
        args = parser.parse_args(argv)
        command = parser.get_command(args.command)
        if command is None:
            parser.print_help()
            return -1

        if args.nvtest_profile:
            return invoke_profiled_command(command, args)
        else:
            return invoke_command(command, args)
    finally:
        os.chdir(config.invocation_dir)


class NVTestCommand:
    def __init__(self, command_name: str, debug: bool = False) -> None:
        from _nvtest.util.executable import Executable

        command_module = cmd.get_command(command_name)
        if command_module is None:
            raise ValueError(f"Unknown command {command_name!r}")
        self.python = Executable(sys.executable)
        self.python.add_default_args("-m", "nvtest")
        if debug:
            self.python.add_default_args("-d")
        self.python.add_default_args(command_name)

    @property
    def returncode(self) -> int:
        return self.python.returncode

    def __call__(self, *args: str, fail_on_error: bool = True) -> None:
        self.python(*args, fail_on_error=fail_on_error)


def invoke_command(command: FunctionType, args: argparse.Namespace) -> int:
    return command(args)


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
        nlines = int(args.lines)
    except ValueError:
        if args.lines != "all":
            raise ValueError("Invalid number for --lines: %s" % args.lines)
        nlines = -1

    with Profiler(nlines=nlines):
        rc = invoke_command(command, args)
    return rc


def load_plugins(paths: list[str]) -> None:
    disable, dirs = [], []
    for path in paths:
        if path.startswith("no:"):
            disable.append(path)
        elif not os.path.exists(path):
            logging.warning(f"{path}: plugin directory not found")
        else:
            dirs.append(path)
    plugin.load_builtin_plugins(disable=disable)
    plugin.load_from_entry_points(disable=disable)
    for dir in dirs:
        path = os.path.abspath(dir)
        plugin.load_from_directory(path)


def console_main() -> int:
    """The CLI entry point of nvtest.

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
        if config.get("config:debug"):
            raise
        logging.error(e.args[0])
        return 4
    except KeyboardInterrupt:
        if config.get("config:debug"):
            raise
        sys.stderr.write("\n")
        logging.error("Keyboard interrupt.")
        return signal.SIGINT.value
    except SystemExit as e:
        if config.get("config:debug"):
            traceback.print_exc()
        if isinstance(e.code, int):
            return e.code
        return 1
    except Exception as e:
        if config.get("config:debug"):
            raise
        logging.error(str(e))
        return 3
