import argparse
import os
import re
import shlex
from typing import TYPE_CHECKING
from typing import Any
from typing import Union

__all__ = [
    "PathSpec",
    "setdefault",
    "add_mark_arguments",
    "add_work_tree_arguments",
    "add_resource_arguments",
    "add_batch_arguments",
]


from ... import config
from ...resources import ResourceHandler
from ...third_party.color import colorize
from ...util.string import ilist
from ...util.string import strip_quotes
from ...util.time import time_in_seconds
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
        dest="rh",
        default=None,
        help=ResourceSetter.help_page("-l"),
    )


def add_batch_arguments(parser: "Parser") -> None:
    group = parser.add_argument_group("batch control")
    group.add_argument("--batched-invocation", default=False, help=argparse.SUPPRESS)
    group.add_argument(
        "-b",
        action=BatchSetter,
        metavar="resource",
        dest="rh",
        default=None,
        help=BatchSetter.help_page("-b"),
    )


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        key, value = ResourceSetter.parse(values)
        rh = getattr(args, self.dest, None) or ResourceHandler()
        rh.set(key, value)
        setattr(args, self.dest, rh)

    @staticmethod
    def help_page(flag: str) -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        text = """\
Defines resources that are required by the test session and establishes limits
to the amount of resources that can be consumed. The %(r_arg)s argument is of
the form: ``%(r_form)s``.  The possible ``%(r_form)s`` settings are\n\n
• ``%(f)s session:workers=N``: Execute the test session asynchronously using a pool of at most N workers [default: auto]\n\n
• ``%(f)s session:cpu_count=N``: Occupy at most N cpu cores at any one time.\n\n
• ``%(f)s session:cpu_ids=L``: Comma separated list of CPU ids available to the session, mutually exclusive with session:cpu_count.\n\n
• ``%(f)s session:gpu_count=N``: Occupy at most N gpus at any one time.\n\n
• ``%(f)s session:gpu_ids=L``: Comma separated list of GPU ids available to the session, mutually exclusive with session:gpu_count.\n\n
• ``%(f)s session:timeout=T``: Set a timeout on test session execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s) [default: 60m]\n\n
• ``%(f)s test:cpus=[n:]N``: Skip tests requiring less than n and more than N cpu cores [default: 0 and machine cpu count]\n\n
• ``%(f)s test:gpus=N``: Skip tests requiring more than N gpus.\n\n
• ``%(f)s test:timeout=T``: Set a timeout on any single test execution in seconds (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s)\n\n
• ``%(f)s test:timeoutx=R``: Set a timeout multiplier for all tests [default: 1.0]\n\n
""" % {"f": flag, "r_form": bold("scope:type=value"), "r_arg": bold(f"{flag} resource")}
        return text

    @staticmethod
    def parse(arg: str) -> tuple[str, Any]:
        if match := re.search(r"^session:(cpu_count|cpus|cores|processors)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session:cpu_count", int(raw))
        elif match := re.search(r"^session:cpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session:cpu_ids", ints)
        elif match := re.search(r"^session:gpu_ids[:=](.*)$", arg):
            raw = match.group(1)
            ints = ilist(raw.strip())
            return ("session:gpu_ids", ints)
        elif match := re.search(r"^session:workers[:=](\d+)$", arg):
            raw = match.group(1)
            return ("session:workers", int(raw))
        elif match := re.search(r"^session:(gpu_count|devices|gpus)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("session:gpu_count", int(raw))
        elif match := re.search(r"^test:(devices|gpus)[:=](\d+)$", arg):
            raw = match.group(2)
            return ("test:gpus", int(raw))
        elif match := re.search(r"^test:(cpus|cores|processors)[:=]:?(\d+)$", arg):
            raw = match.group(2)
            return ("test:cpus", [0, int(raw)])
        elif match := re.search(r"^test:(cpus|cores|processors)[:=](\d+):$", arg):
            raw = match.group(2)
            return ("test:cpus", [int(raw), config.get("machine:cpu_count")])
        elif match := re.search(r"^test:(cpus|cores|processors)[:=](\d+):(\d+)$", arg):
            _, a, b = match.groups()
            return ("test:cpus", [int(a), int(b)])
        elif match := re.search(r"^(session|test):timeout[:=](.*)$", arg):
            scope, raw = match.group(1), strip_quotes(match.group(2))
            return (f"{scope}:timeout", time_in_seconds(raw))
        elif match := re.search(r"^test:timeoutx[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("test:timeoutx", time_in_seconds(raw))
        else:
            raise ValueError(f"invalid resource arg: {arg!r}")


class BatchSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        type, value = BatchSetter.parse(values)
        rh = getattr(args, self.dest, None) or ResourceHandler()
        rh.set(f"batch:{type}", value)
        rh.set("batch:batched", True)
        setattr(args, self.dest, rh)
        setattr(args, "batched_invocation", True)

    @staticmethod
    def parse(arg: str) -> tuple[str, Any]:
        if match := re.search(r"^length[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            length = time_in_seconds(raw)
            if length <= 0:
                raise ValueError("batch length <= 0")
            return ("length", time_in_seconds(raw))
        elif match := re.search(r"^(count|workers)[:=](\d+)$", arg):
            type, raw = match.groups()
            return (type, int(raw))
        elif match := re.search(r"^scheduler[:=](\w+)$", arg):
            raw = match.group(1)
            return ("scheduler", str(raw))
        elif match := re.search(r"^args[:=](.*)$", arg):
            raw = strip_quotes(match.group(1))
            return ("args", shlex.split(raw))
        else:
            raise ValueError(f"invalid batch arg: {arg!r}")

    @staticmethod
    def help_page(flag: str) -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        resource_help = """\
Defines how to batch test cases. The %(r_arg)s argument is of the form: ``%(r_form)s``.
The possible possible ``%(r_form)s`` settings are\n\n
• ``%(f)s count=N``: Execute tests in N batches.\n\n
• ``%(f)s length=T``: Execute tests in batches having runtimes of approximately T seconds.  [default: 30 min]\n\n
• ``%(f)s scheduler=S``: Use scheduler 'S' to run the test batches.\n\n
• ``%(f)s workers=N``: Execute tests in a batch asynchronously using a pool of at most N workers [default: auto]\n\n
• ``%(f)s args=A``: Any additional args 'A' are passed directly to the scheduler, for example,
  ``%(f)s args=--account=ABC`` will pass ``--account=ABC`` to the scheduler
""" % {"f": flag, "r_form": bold("type:value"), "r_arg": bold(f"{flag} resource")}
        return resource_help


def filter_cases_by_path(cases: list["TestCase"], pathspec: str) -> list["TestCase"]:
    prefix = os.path.abspath(pathspec)
    return [c for c in cases if c.matches(pathspec) or c.exec_dir.startswith(prefix)]


def filter_cases_by_status(cases: list["TestCase"], status: Union[tuple, str]) -> list["TestCase"]:
    if isinstance(status, str):
        status = (status,)
    return [c for c in cases if c.status.value in status]


class ResourceError(Exception):
    def __init__(self, action, values, message):
        opt = "/".join(action.option_strings)
        super().__init__(f"{opt} {values}: {message}")
