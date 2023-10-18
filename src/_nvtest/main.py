import argparse
import os
import pstats
import sys
from types import FunctionType
from typing import Optional

from . import plugin
from .command import add_commands
from .config.argparsing import make_argument_parser
from .config.argparsing import stat_names
from .util import tty


def main(argv: Optional[list[str]] = None) -> int:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).

    :returns: An exit code.
    """
    parser = make_argument_parser()

    load_plugins()
    add_commands(parser)

    args = parser.parse_args(argv)
    command = parser.get_command(args.command)

    if args.nvtest_profile:
        return _profile_wrapper(command, args)
    else:
        return invoke_command(command, args)


def invoke_command(command: FunctionType, args: argparse.Namespace) -> int:
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
