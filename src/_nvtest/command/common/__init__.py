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


from ...third_party.color import colorize
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
        "For example: -k 'key1 and not key2'.",
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
        scope, type, value = self.parse_path(values)
        self.set_resource_args(args, scope, type, value)

    def set_resource_args(self, args, scope, type, value):
        resourceinfo = getattr(args, self.dest, None) or resource.ResourceInfo()
        resourceinfo.set(scope, type, value)
        setattr(args, self.dest, resourceinfo)

    @staticmethod
    def type_map(type: str) -> str:
        return {"cores": "cpus", "processors": "cpus", "gpus": "devices"}.get(type, type)

    def parse_path(self, path: str) -> tuple[str, str, str]:
        key, value = path.split("=", 1)
        scope, type = key.split(":")
        type = self.type_map(type)
        return scope, type, value

    @staticmethod
    def help_page() -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        resource_help = """\
Defines resources that are required by the test session and establishes limits
to the amount of resources that can be consumed. The %(r_arg)s argument is of
the form: %(r_form)s.  The possible possible %(r_form)s settings are\n\n
• -l session:workers=N: Execute the test session asynchronously using a pool of at most N workers [default: auto]\n
• -l session:cpus=N: Occupy at most N cpu cores at any one time.\n
• -l session:devices=N: Occupy at most N devices at any one time.\n
• -l session:timeout=T: Set a timeout on test session execution in seconds (accepts human readable expressions like 1s, 1 hr, 2 hrs, etc) [default: 60 min]\n
• -l test:cpus=N: Skip tests requiring more than N cpu cores.\n
• -l test:devices=N: Skip tests requiring more than N devices.\n
• -l test:timeout=T: Set a timeout on any single test execution in seconds (accepts human readable expressions like 1s, 1 hr, 2 hrs, etc) [default: 60 min]\n
• -l batch:workers=N: Execute the batch asynchronously using a pool of at most N workers [default: auto]\n
""" % {"r_form": bold("scope:type=value"), "r_arg": bold("-l resource")}
        return resource_help


class BatchSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        type, value = self.parse_path(values)
        self.set_batch_args(args, type, value)

    def set_batch_args(self, args, type, value):
        batchinfo = getattr(args, self.dest, None) or resource.BatchInfo()
        batchinfo.set(type, value)
        setattr(args, self.dest, batchinfo)

    def parse_path(self, path: str) -> tuple[str, str]:
        type, value = path.split("=", 1)
        if type == "args":
            value = strip_quotes(value)
        return type, value

    @staticmethod
    def help_page() -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        resource_help = """\
Defines how to batch test cases. The %(r_arg)s argument is of the form: %(r_form)s.
The possible possible %(r_form)s settings are\n\n
• -b count=N: Execute tests in N batches.\n
• -b limit=T: Execute tests in batches having runtimes of approximately T seconds.  [default: 30 min]
• -b scheduler=S: Use scheduler 'S' to run the test batches.\n
• -b,args=A: Any additional args 'A' are passed directly to the scheduler, for example,
  -b args=--account=ABC will pass --account=ABC to the scheduler\n
""" % {"r_form": bold("type:value"), "r_arg": bold("-b resource")}
        return resource_help


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.matches(pathspec) or c.exec_dir.startswith(prefix)]


def filter_cases_by_status(cases: list["TestCase"], status: Union[tuple, str]) -> list["TestCase"]:
    if isinstance(status, str):
        status = (status,)
    return [c for c in cases if c.status.value in status]


def split_on_comma(string: str) -> list[str]:
    if not string:
        return []
    single_quote = "'"
    double_quote = '"'
    args: list[str] = []
    tokens = iter(string[1:] if string[0] == "," else string)
    arg = ""
    quoted = None
    while True:
        try:
            token = next(tokens)
        except StopIteration:
            args.append(arg)
            break
        if not quoted and token == ",":
            args.append(arg)
            arg = ""
            continue
        else:
            arg += token
        if token in (single_quote, double_quote):
            if quoted is None:
                # starting a quoted string
                quoted = token
            elif token == quoted:
                # ending a quoted string
                quoted = None
    return args


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
