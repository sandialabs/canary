import argparse
import os
import pstats
import signal
import sys
import traceback
from types import FunctionType
from typing import Optional

from . import config
from . import plugin
from .command import add_commands
from .config.argparsing import make_argument_parser
from .config.argparsing import stat_names
from .error import StopExecution
from .session import ExitCode
from .util import tty


def main(argv: Optional[list[str]] = None) -> int:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).

    :returns: An exit code.
    """
    parser = make_argument_parser()

    invocation_dir = os.getcwd()
    pre = parser.preparse()

    try:
        os.chdir(pre.C or invocation_dir)

        load_plugins()
        add_commands(parser)

        args = parser.parse_args(argv)
        command = parser.get_command(args.command)

        if args.nvtest_profile:
            return _profile_wrapper(command, args)
        else:
            return invoke_command(command, args)
    finally:
        os.chdir(invocation_dir)


def invoke_command(command: FunctionType, args: argparse.Namespace) -> int:
    config.set_main_options(args)
    return command(args)


def _profile_wrapper(command, args):
    import cProfile

    try:
        nlines = int(args.lines)
    except ValueError:
        if args.lines != "all":
            tty.die("Invalid number for --lines: %s" % args.lines)
        nlines = -1

    # allow comma-separated list of fields
    sortby = ["time"]
    if args.sorted_profile:
        sortby = args.sorted_profile.split(",")
        for stat in sortby:
            if stat not in stat_names:
                tty.die("Invalid sort field: %s" % stat)

    try:
        # make a profiler and run the code.
        pr = cProfile.Profile()
        pr.enable()
        return invoke_command(command, args)

    finally:
        pr.disable()

        # print out profile stats.
        stats = pstats.Stats(pr)
        stats.sort_stats(*sortby)
        stats.print_stats(nlines)


def load_plugins() -> None:
    import _nvtest.plugins

    path = _nvtest.plugins.__path__
    namespace = _nvtest.plugins.__name__
    plugin.load(path, namespace)


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
        if e.exit_code == ExitCode.OK:
            tty.info(e.message)
        else:
            tty.error(e.message)
        return 1
    except TimeoutError as e:
        if config.get("config:debug"):
            raise
        tty.error(e.args[0])
        return 4
    except KeyboardInterrupt:
        if config.get("config:debug"):
            raise
        sys.stderr.write("\n")
        tty.error("Keyboard interrupt.")
        return signal.SIGINT.value
    except SystemExit as e:
        if config.get("config:debug"):
            traceback.print_exc()
        return e.code
    except Exception as e:
        if config.get("config:debug"):
            raise
        tty.error(e)
        return 3
