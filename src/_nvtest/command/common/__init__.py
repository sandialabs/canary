import argparse
import io
import os
import tokenize
from typing import TYPE_CHECKING
from typing import Union

__all__ = [
    "PathSpec",
    "setdefault",
    "add_mark_arguments",
    "add_work_tree_arguments",
    "add_resource_arguments",
    "add_batch_arguments",
]


from ...util import resource
from .pathspec import PathSpec
from .pathspec import setdefault

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser
    from _nvtest.test.case import TestCase


def add_mark_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("filtering")
    group.add_argument(
        "-k",
        dest="keyword_expr",
        default=None,
        metavar="expression",
        help="Only run tests matching given keyword expression. "
        "For example: ``-k 'key1 and not key2'``.",
    )
    group.add_argument(
        "-o",
        dest="on_options",
        default=[],
        metavar="option",
        action="append",
        help="Turn option(s) on, such as ``-o dbg`` or ``-o intel``",
    )
    group.add_argument(
        "-p",
        dest="parameter_expr",
        metavar="expression",
        default=None,
        help="Filter tests by parameter name and value, such as ``-p np=8`` or ``-p np<8``",
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
    group = parser.add_argument_group("resource control")
    group.add_argument(
        "-l",
        action=ResourceSetter,
        metavar="resource",
        dest="resourceinfo",
        default=None,
        help=ResourceSetter.help_page(),
    )


def add_batch_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("batch control")
    group.add_argument(
        "-b",
        action=BatchSetter,
        metavar="resource",
        dest="batchinfo",
        default=None,
        help=BatchSetter.help_page(),
    )


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        key, value = resource.ResourceInfo.parse(values)
        resourceinfo = getattr(args, self.dest, None) or resource.ResourceInfo()
        resourceinfo.set(key, value)
        setattr(args, self.dest, resourceinfo)

    @staticmethod
    def help_page() -> str:
        return resource.ResourceInfo.cli_help("-l")


class BatchSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        type, value = resource.BatchInfo.parse(values)
        batchinfo = getattr(args, self.dest, None) or resource.BatchInfo()
        batchinfo.set(type, value)
        setattr(args, self.dest, batchinfo)

    @staticmethod
    def help_page() -> str:
        return resource.BatchInfo.cli_help("-b")


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.matches(pathspec) or c.exec_dir.startswith(prefix)]


def filter_cases_by_status(cases: list["TestCase"], status: Union[tuple, str]) -> list["TestCase"]:
    if isinstance(status, str):
        status = (status,)
    return [c for c in cases if c.status.value in status]


def strip_quotes(arg: str) -> str:
    s_quote, d_quote = "'''", '"""'
    tokens = tokenize.generate_tokens(io.StringIO(arg).readline)
    token = next(tokens)
    while token.type == tokenize.ENCODING:
        token = next(tokens)
    s = token.string
    if token.type == tokenize.STRING:
        if s.startswith((s_quote, d_quote)):
            return s[3:-3]
        return s[1:-1]
    return arg


class ResourceError(Exception):
    def __init__(self, action, values, message):
        opt = "/".join(action.option_strings)
        super().__init__(f"{opt} {values}: {message}")
