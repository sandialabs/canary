import argparse
from typing import TYPE_CHECKING

import _nvtest.config as config
from _nvtest.util import tty
from _nvtest.util.time import time_in_seconds
from _nvtest.util.tty.color import colorize

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser

default_timeout = 60 * 60


def setdefault(obj, attr, default):
    if not hasattr(obj, attr):
        setattr(obj, attr, default)
    return getattr(obj, attr)


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
        default=None,
        help=colorize(
            "Defines resources that are required by the test session and "
            "establishes limits to the amount of resources that can be consumed. "
            "The @*{resource} argument is of the form: @*{[scope:]type:value}, where "
            "@*{scope} (optional) is one of session, test, or batch, (session is "
            "assumed if not provided); @*{type} is one of workers, cpus, or devices; "
            "and @*{value} is an integer value. By default, nvtest will determine and "
            "all available cpu cores.\n\n\n\n@*{Examples}\n\n"
            "@*{* -l test:cpus:5}: Skip tests requiring more than 5 cpu cores.\n\n"
            "@*{* -l session:cpus:5}: Occupy at most 5 cpu cores at any one time.\n\n"
            "@*{* -l test:devices:2}: Skip tests requiring more than 2 devices.\n\n"
            "@*{* -l session:devices:3}: Occupy at most 3 devices at any one time.\n\n"
            "@*{* -l session:workers:8}: Execute tests/batches asynchronously using "
            "a pool of at most 8 workers\n\n"
            "@*{* -l batch:count:8}: Execute tests in 8 batches.\n\n"
            "@*{* -l 'batch:time:30 min'}: Execute tests in batches whose runtime is "
            "approximately 30 minutes.\n\n"
        ),
    )


def set_default_resource_args(args: argparse.Namespace) -> None:
    cpu_count = config.get("machine:cpu_count")
    cpus_per_test = setdefault(args, "cpus_per_test", None)
    cpus_per_session = setdefault(args, "cpus_per_session", None)
    if cpus_per_test is not None:
        if cpus_per_test > cpu_count:
            tty.die("-l test:cpus cannot exceed machine:cpu_count")
    if cpus_per_session is not None:
        if cpus_per_session > cpu_count:
            tty.die("-l session:cpus cannot exceed machine:cpu_count")
        if cpus_per_test is not None and cpus_per_test > cpus_per_session:
            tty.die("-l test:cpus cannot exceed session:cpus")

    device_count = config.get("machine:device_count")
    devices_per_test = setdefault(args, "devices_per_test", None)
    devices_per_session = setdefault(args, "devices_per_session", None)
    if devices_per_test is not None:
        if devices_per_test > device_count:
            tty.die("-l test:devices cannot exceed machine:device_count")
    if devices_per_session is not None:
        if devices_per_session > device_count:
            tty.die("-l session:devices cannot exceed machine:device_count")
        if devices_per_test is not None and devices_per_test > devices_per_session:
            tty.die("-l test:devices cannot exceed session:devices")

    workers_per_session = setdefault(args, "workers_per_session", None)
    if workers_per_session is not None:
        if workers_per_session > cpu_count:
            tty.die("-l session:workers cannot exceed machine:cpu_count")
        if cpus_per_session is not None and workers_per_session > cpus_per_session:
            tty.die("-l session:workers cannot exceed session:cpus")


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        scope, type, value = self.parse_path(values)
        if scope == "batch":
            self.set_batch_args(args, scope, type, value)
        else:
            self.set_resource_args(args, scope, type, value)

    def set_batch_args(self, args, scope, type, value):
        assert scope == "batch"
        conflicting_type = "time" if type == "count" else "count"
        if hasattr(args, f"batch_{conflicting_type}"):
            raise ValueError("batch:count and batch:time are mutually exclusive")
        setattr(args, f"batch_{type}", value)

    def set_resource_args(self, args, scope, type, value):
        type = {"cores": "cpus", "gpus": "devices"}.get(type, type)
        setattr(args, f"{type}_per_{scope}", value)

    def parse_path(self, path):
        components = [_.strip() for _ in path.split(":") if _.split()]
        if len(components) == 2:
            components.insert(0, "session")
        elif len(components) != 3:
            raise ResourceError(self, path, "invalid resource spec")
        scope, type, string = components
        if scope in ("session", "test"):
            if type not in ("cores", "cpus", "devices", "gpus", "workers"):
                raise ResourceError(self, path, f"invalid type {type!r}")
        elif scope == "batch":
            if type not in ("count", "time"):
                raise ResourceError(self, path, f"invalid type {type!r}")
        else:
            raise ResourceError(self, path, f"invalid scope {scope!r}")
        if type == "workers" and scope != "session":
            raise ResourceError(
                self, path, f"invalid scope {scope!r} (expected session)"
            )
        if type == "time":
            value = time_in_seconds(string)
        else:
            try:
                value = int(string)
            except ValueError:
                raise ResourceError(self, path, f"invalid int {string!r}")
        return scope, type, value


class ResourceError(Exception):
    def __init__(self, action, values, message):
        opt = "/".join(action.option_strings)
        super().__init__(f"{opt} {values}: {message}")
