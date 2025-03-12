import argparse
import os
import re
from typing import TYPE_CHECKING

from ....util.time import time_in_seconds

__all__ = [
    "PathSpec",
    "setdefault",
    "add_filter_arguments",
    "add_work_tree_arguments",
    "add_resource_arguments",
]


from .pathspec import PathSpec
from .pathspec import setdefault

if TYPE_CHECKING:
    from ....config.argparsing import Parser
    from ....test.case import TestCase


def add_filter_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("filtering")
    group.add_argument(
        "-k",
        dest="keyword_exprs",
        metavar="expression",
        action="append",
        help="Only run tests matching given keyword expression. "
        "For example: `-k 'key1 and not key2'`.",
    )
    group.add_argument(
        "-R",
        dest="rerun_all_testcases",
        action="store_true",
        help="Rerun tests.  Normally, tests are not run if they previously completed",
    )
    group.add_argument(
        "-o",
        dest="on_options",
        default=[],
        metavar="option",
        action="append",
        help="Turn option(s) on, such as '-o dbg' or '-o intel'",
    )
    group.add_argument(
        "-p",
        dest="parameter_expr",
        metavar="expression",
        help="Filter tests by parameter name and value, such as '-p cpus=8' or '-p cpus<8'",
    )
    group.add_argument(
        "-S",
        "--regex",
        dest="regex_filter",
        metavar="regex",
        help="Include tests containing the regular expression regex in at least 1 of its "
        "file assets.  regex is a python regular expression, see "
        "https://docs.python.org/3/library/re.html",
    )


def add_work_tree_arguments(parser: "Parser") -> None:
    parser.add_argument(
        "-w",
        dest="wipe",
        default=False,
        action="store_true",
        help="Remove test execution directory, if it exists [default: %(default)s]",
    )
    parser.add_argument(
        "-d",
        "--work-tree",
        dest="work_tree",
        metavar="directory",
        help="Set the path to the working tree. It can be an absolute path or a "
        "path relative to the current working directory. [default: ./TestResults]",
    )


def add_resource_arguments(parser: "Parser") -> None:
    from .resource import BatchResourceSetter
    from .resource import DeprecatedResourceSetter

    group = parser.add_argument_group("resource control")
    group.add_argument("-l", help=argparse.SUPPRESS, action=DeprecatedResourceSetter)
    group.add_argument(
        "--workers",
        metavar="N",
        type=int,
        help="Execute the test session asynchronously using a pool of at most N workers",
    )
    group.add_argument(
        "--timeout",
        "--session-timeout",
        dest="session_timeout",
        metavar="T",
        type=time_in_seconds,
        help="Set a timeout on test session execution in seconds "
        "(accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: None]",
    )
    group.add_argument(
        "--test-timeout",
        metavar="type:T",
        action=TimeoutResource,
        help="Set the timeout for tests of type.  "
        "Type is one of 'fast', 'long', 'default', or 'ctest'"
        "(T accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: 5m]",
    )
    group.add_argument(
        "--timeout-multiplier",
        metavar="X",
        type=time_in_seconds,
        help="Set a timeout multiplier for all tests [default: 1.0]",
    )

    group = parser.add_argument_group("batch control")
    group.add_argument(
        "-b",
        action=BatchResourceSetter,
        metavar="resource",
        dest="batch",
        help=BatchResourceSetter.help_page("-b"),
    )


class TimeoutResource(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        if match := re.search(r"^(long|default|fast|ctest)[:=](.*)$", values):
            type = match.group(1)
            value = time_in_seconds(match.group(2))
        else:
            raise ValueError(f"Incorrect test timeout spec: {values}, expected 'type:value'")
        choices = ("fast", "long", "default", "ctest", "session")
        if type.lower() not in choices:
            s = ", ".join(repr(c) for c in choices)
            raise ValueError(
                f"argument {option_string}: invalid choice: {type!r} (choose from {s})"
            )
        elif type.lower() == "session":
            args.session_timeout = value
        else:
            timeout_resources = getattr(args, self.dest, None) or {}
            timeout_resources[type] = value
            setattr(args, self.dest, timeout_resources)


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.matches(pathspec) or c.working_directory.startswith(prefix)]


def filter_cases_by_status(cases: list["TestCase"], status: tuple | str) -> list["TestCase"]:
    if isinstance(status, str):
        status = (status,)
    return [c for c in cases if c.status.value in status]


def load_session(root: str | None = None, mode: str = "r"):
    from ....session import Session
    from ....util import logging

    with logging.level(logging.WARNING):
        return Session(root or os.getcwd(), mode=mode)
