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
    "add_filter_arguments",
    "add_work_tree_arguments",
    "add_resource_arguments",
]


if TYPE_CHECKING:
    from ....config.argparsing import Parser
    from ....testcase import TestCase

logger = logging.get_logger(__name__)


def add_filter_arguments(parser: "Parser", tagged: bool = True) -> None:
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
    if tagged:
        group.add_argument(
            "--tag",
            help="Tag this test case selection for future runs [default: False]",
        )


def add_work_tree_arguments(parser: "Parser") -> None:
    parser.add_argument(
        "-w",
        dest="wipe",
        default=False,
        action="store_true",
        help="Remove test execution directory, if it exists [default: %(default)s]",
    )
    parser.add_argument("-d", "--work-tree", dest="work_tree", help=argparse.SUPPRESS)


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
        help=f"Set the timeout for {bold('type')} (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s).\n\n"
        f"• type={bold('session')}, the timeout T is applied to the entire test session.\n\n"
        f"• type={bold('multiplier')}, the multiplier T is applied to each test's timeout.\n\n"
        f"• type={bold('*')}, the timeout T is applied to all test cases.\n\n"
        f"• type={bold('batch')}, choices for T are 'conservative' to use a conservative "
        "estimate for batch timeouts (queue times) or 'aggressive'.\n\n"
        f"Otherwise, a timeout of T is applied to tests having keyword {bold('type')}.\n\n"
        "For example, --timeout fast=2 would apply a timeout of 2 seconds to all tests having "
        "the 'fast' keyword; common types are fast, long, default, and ctest. ",
    )
    group.add_argument(
        "--no-incremental",
        action="store_true",
        default=False,
        help="Don't use the .canary_cache to infer testcase runtimes",
    )
    group.add_argument("--session-timeout", action=TimeoutResource, help=argparse.SUPPRESS)
    group.add_argument("--test-timeout", action=TimeoutResource, help=argparse.SUPPRESS)
    group.add_argument("--timeout-multiplier", action=TimeoutResource, help=argparse.SUPPRESS)


class TimeoutResource(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        if option_string == "--session-timeout":
            logger.warning(
                f"option --session-timeout is deprecated, use --timeout session={values}"
            )
            type = "session"
            value = time_in_seconds(values)
        elif option_string == "--timeout-multiplier":
            logger.warning(
                f"option --timeout-multiplier is deprecated, use --timeout multiplier={values}"
            )
            type = "multiplier"
            value = time_in_seconds(values)
        elif option_string == "--test-timeout":
            logger.warning(f"option --test-timeout is deprecated, use --timeout all={values}")
            type = "*"
            value = time_in_seconds(values)
        else:
            if match := re.search(r"^(\*|\w*)[:=](.*)$", values):
                type = match.group(1).lower()
                value = time_in_seconds(match.group(2))
                if type == "all":
                    type = "*"
            else:
                raise ValueError(f"Incorrect test timeout spec: {values}, expected 'type=value'")
        timeouts = getattr(args, "timeout", None) or {}
        timeouts[type] = value
        setattr(args, "timeout", timeouts)


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.workspace.dir.relative_to(prefix)]


def bold(arg: str) -> str:
    if os.getenv("COLOR_WHEN", "auto") == "never":
        return f"**{arg}**"
    return colorize("@*{%s}" % arg)
