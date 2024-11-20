import argparse
import os
from typing import TYPE_CHECKING

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
    from ...config.argparsing import Parser
    from ...test.case import TestCase


def add_filter_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("filtering")
    group.add_argument(
        "-k",
        dest="keyword_expr",
        default=None,
        metavar="expression",
        help="Only run tests matching given keyword expression. "
        "For example: `-k 'key1 and not key2'`.",
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
        default=None,
        help="Filter tests by parameter name and value, such as '-p np=8' or '-p np<8'",
    )
    group.add_argument(
        "-R",
        dest="regex_filter",
        metavar="regex",
        default=None,
        help="Include tests containing the regular expression regex in at least 1 of its "
        "resources.  regex is a python regular expression, see "
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
        default=None,
        help="Set the path to the working tree. It can be an absolute path or a "
        "path relative to the current working directory. [default: ./TestResults]",
    )


def add_resource_arguments(parser: "Parser") -> None:
    from .resource import ResourceSetter

    group = parser.add_argument_group("resource control")
    group.add_argument(
        "-l",
        action=ResourceSetter,
        metavar="resource",
        dest="resource_setter",
        default=None,
        help=ResourceSetter.help_page("-l"),
    )

    group.add_argument("--batched-invocation", default=False, help=argparse.SUPPRESS)
    group.add_argument(
        "-b",
        action=ResourceSetter,
        metavar="resource",
        dest="resource_setter",
        default=None,
        help=argparse.SUPPRESS,
    )


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.matches(pathspec) or c.exec_dir.startswith(prefix)]


def filter_cases_by_status(cases: list["TestCase"], status: tuple | str) -> list["TestCase"]:
    if isinstance(status, str):
        status = (status,)
    return [c for c in cases if c.status.value in status]
