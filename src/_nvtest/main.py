import argparse
import os
import shlex
import signal
import sys
import traceback
from typing import TYPE_CHECKING
from typing import Sequence

import hpc_connect

from . import config
from . import plugin
from .config.argparsing import make_argument_parser
from .error import StopExecution
from .third_party.monkeypatch import monkeypatch
from .util import logging

if TYPE_CHECKING:
    from .command.base import Command


reraise: bool = False


def main(argv: Sequence[str] | None = None) -> int:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).

    :returns: An exit code.
    """
    if "NVTEST_LEVEL" not in os.environ:
        os.environ["NVTEST_LEVEL"] = "0"

    with NVTestMain(argv) as m:
        parser = make_argument_parser()
        parser.add_all_commands()
        with monkeypatch.context() as mp:
            mp.setattr(parser, "add_argument", parser.add_plugin_argument)
            for hook in plugin.hooks():
                hook.main_setup(parser)
        args = parser.parse_args(m.argv)
        if args.echo:
            a = [os.path.join(sys.prefix, "bin/nvtest")] + [_ for _ in m.argv if _ != "--echo"]
            logging.emit(shlex.join(a) + "\n")
        setup_hpc_connect(args)
        config.set_main_options(args)
        config.validate()
        command = parser.get_command(args.command)
        if command is None:
            parser.print_help()
            return -1
        if args.nvtest_profile:
            return invoke_profiled_command(command, args)
        else:
            return invoke_command(command, args)


class NVTestMain:
    """Set up and teardown this nvtest session"""

    def __init__(self, argv: Sequence[str] | None = None) -> None:
        self.argv: Sequence[str] = argv or sys.argv[1:]
        self.invocation_dir = self.working_dir = os.getcwd()

    def __enter__(self) -> "NVTestMain":
        global reraise
        if "GITLAB_CI" in os.environ:
            reraise = True
        parser = make_argument_parser()
        parser.add_all_commands()
        # preparse to get the list of plugins to load and/or not load
        args = parser.preparse(self.argv)
        if args.debug:
            reraise = True
        if args.C:
            self.working_dir = args.C
        os.chdir(self.working_dir)
        return self

    def __exit__(self, ex_type, ex_value, ex_traceback):
        os.chdir(self.invocation_dir)


class NVTestCommand:
    def __init__(self, command_name: str, debug: bool = False) -> None:
        plugin.load_from_entry_points()
        for command_class in plugin.commands():
            if command_class.cmd_name() == command_name:
                self.command = command_class()
                break
        else:
            raise ValueError(f"Unknown command {command_name!r}")
        self.debug = debug
        self.returncode = -1

    def __call__(self, *args_in: str, fail_on_error: bool = True) -> int:
        try:
            save_debug: bool | None = None
            if self.debug:
                save_debug = config.debug
                config.debug = True
            parser = make_argument_parser()
            parser.add_command(self.command)
            argv = [self.command.cmd_name()] + list(args_in)
            args = parser.parse_args(argv)
            setup_hpc_connect(args)
            config.set_main_options(args)
            config.validate()
            load_plugins(args.plugin_dirs or [])
            rc = self.command.execute(args)
            self.returncode = rc
        except Exception:
            if fail_on_error:
                raise
            self.returncode = 1
        finally:
            if save_debug is not None:
                config.debug = save_debug
        return self.returncode


def setup_hpc_connect(args: argparse.Namespace) -> None:
    """Set the hpc_connect library"""
    debug = getattr(args, "debug", False)
    # main options have not been set, fake the logger to print output
    level = logging.FATAL if debug else logging.TRACE
    log = lambda message: logging.log(level, message, prefix="@*g{==>}")
    # main options have not yet been set
    if batch_scheduler := getattr(args, "batch_scheduler", None):
        if batch_scheduler == "null":
            return
        log(f"Setting up HPC Connect for {batch_scheduler}")
        hpc_connect.set(scheduler=batch_scheduler)  # type: ignore
        log(f"  HPC connect: node count: {hpc_connect.scheduler.config.node_count}")
        log(f"  HPC connect: CPUs per node: {hpc_connect.scheduler.config.cpus_per_node}")
        log(f"  HPC connect: GPUs per node: {hpc_connect.scheduler.config.gpus_per_node}")
        config.update_resource_counts(
            node_count=hpc_connect.scheduler.config.node_count,  # type: ignore
            cpus_per_node=hpc_connect.scheduler.config.cpus_per_node,  # type: ignore
            gpus_per_node=hpc_connect.scheduler.config.gpus_per_node,  # type: ignore
        )


def invoke_command(command: "Command", args: argparse.Namespace) -> int:
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
            disable.append(path[3:])
        elif not os.path.exists(path):
            logging.warning(f"{path}: plugin directory not found")
        else:
            dirs.append(path)
    plugin.load_from_entry_points(disable=disable)
    for dir in dirs:
        path = os.path.abspath(dir)
        plugin.load_from_path(path)


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
