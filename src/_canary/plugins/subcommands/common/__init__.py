# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import re
from typing import TYPE_CHECKING

from ....third_party.color import colorize
from ....util import logging
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
    from ....testcase import TestCase


def add_filter_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("filtering")
    group.add_argument(
        "-k",
        dest="keyword_exprs",
        metavar="expression",
        action="append",
        help="Only run tests matching given keyword expression. "
        "For example: `-k 'key1 and not key2'`.  The keyword ``:all:`` matches all tests",
    )
    group.add_argument(
        "-o",
        dest="on_options",
        default=None,
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
        "--search",
        "--regex",
        dest="regex_filter",
        metavar="regex",
        help="Include tests containing the regular expression regex in at least 1 of its "
        "file assets.  regex is a python regular expression, see "
        "https://docs.python.org/3/library/re.html",
    )
    group.add_argument(
        "--rerun-failed",
        nargs=0,
        action=RerunFailed,
        help="Rerun failed tests [default: False]",
    )


class RerunFailed(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        keyword_exprs = getattr(args, "keyword_exprs") or []
        keyword_exprs.append("not success")
        args.keyword_exprs = keyword_exprs


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
    group = parser.add_argument_group("resource control")
    group.add_argument(
        "--workers",
        metavar="N",
        type=int,
        help="Execute the test session asynchronously using a pool of at most N workers",
    )
    group.add_argument(
        "--timeout",
        action=TimeoutResource,
        metavar="type=T",
        help=f"Set the timeout for {bold('type')} "
        "(accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s). "
        f"If type={bold('session')}, the timeout is applied to the entire test session.  "
        f"If type={bold('multiplier')}, the multiplier T is applied to each test's timeout.  "
        f"Otherwise, a timeout of T is applied to tests having keyword {bold('type')}.  "
        "For example, --timeout fast=2 would apply a timeout of 2 seconds to all tests having "
        "the 'fast' keyword; common types are fast, long, default, and ctest.",
    )
    group.add_argument("--session-timeout", action=TimeoutResource, help=argparse.SUPPRESS)
    group.add_argument("--test-timeout", action=TimeoutResource, help=argparse.SUPPRESS)
    group.add_argument("--timeout-multiplier", action=TimeoutResource, help=argparse.SUPPRESS)


class TimeoutResource(argparse.Action):
    _types = ("fast", "long", "default", "session", "ctest", "multiplier")

    def __call__(self, parser, args, values, option_string=None):
        if option_string == "--session-timeout":
            logging.warning(
                f"option --session-timeout is deprecated, use --timeout session={values}"
            )
            type = "session"
            value = time_in_seconds(values)
        elif option_string == "--timeout-multiplier":
            logging.warning(
                f"option --timeout-multiplier is deprecated, use --timeout multiplier={values}"
            )
            type = "multiplier"
            value = time_in_seconds(values)
        else:
            if match := re.search(r"^(\w*)[:=](.*)$", values):
                type = match.group(1).lower()
                value = time_in_seconds(match.group(2))
            else:
                raise ValueError(f"Incorrect test timeout spec: {values}, expected 'type=value'")

        if type == "session":
            args.session_timeout = value
        elif type == "multiplier":
            args.timeout_multiplier = value

        timeouts = getattr(args, "timeouts", None) or {}
        timeouts[type] = value
        setattr(args, "timeouts", timeouts)


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.matches(pathspec) or c.working_directory.startswith(prefix)]


def filter_cases_by_status(cases: list["TestCase"], status: tuple | str) -> list["TestCase"]:
    if isinstance(status, str):
        status = (status,)
    return [c for c in cases if c.status.value in status]


def load_session(root: str | None = None, mode: str = "r"):
    from ....session import Session

    with logging.level(logging.WARNING):
        return Session(root or os.getcwd(), mode=mode)


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("@*{%s}" % arg)
