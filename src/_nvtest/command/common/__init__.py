from typing import TYPE_CHECKING

from _nvtest.util.time import time_in_seconds

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser

default_timeout = 60 * 60


def add_timing_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("timing")
    group.add_argument(
        "--timeout",
        type=time_in_seconds,
        default=default_timeout,
        help="Set a timeout on test execution in seconds (accepts human "
        "readable expressions like 1s, 1 hr, 2 hrs, etc) [default: 1hr]",
    )


def add_mark_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("filtering")
    group.add_argument(
        "-k",
        dest="keyword_expr",
        default="",
        metavar="EXPRESSION",
        help="Only run tests matching given keyword expression. "
        "For example: -k 'key1 and not key2'.",
    )
    group.add_argument(
        "-o",
        dest="on_options",
        default=[],
        metavar="OPTION",
        action="append",
        help="Turn option(s) on, such as '-o dbg' or '-o intel'",
    )
    group.add_argument(
        "-p",
        dest="parameter_expr",
        metavar="P",
        default=None,
        help="Filter tests by parameter name and value, such as '-p np=8' or '-p np<8'",
    )


def add_workdir_arguments(parser: "Parser") -> None:
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
        help="Root path to work (execution) directory [default: ./TestResults]",
    )
