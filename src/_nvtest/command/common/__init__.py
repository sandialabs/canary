import argparse
import os
from typing import TYPE_CHECKING
from typing import Union

import _nvtest.config as config
from _nvtest.util.time import time_in_seconds

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser
    from _nvtest.test.testcase import TestCase

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
        help="Defines resources that are required by the test session and "
        "establishes limits to the amount of resources that can be consumed. ",
    )


def set_default_resource_args(args: argparse.Namespace) -> None:
    def _die(name1, n1, name2, n2):
        raise ValueError("'-l {0}:{1}' must not exceed {2}:{3}".format(name1, n1, name2, n2))

    np = config.get("machine:cpu_count")
    npt = setdefault(args, "cpus_per_test", None)
    nps = setdefault(args, "cpus_per_session", None)
    if npt is not None:
        if npt > np:
            _die("test:cpus", npt, "machine:cpu_count", np)
    if nps is not None:
        if nps > np:
            _die("session:cpus", nps, "machine:cpu_count", np)
        if npt is not None and npt > nps:
            _die("test:cpus", npt, "session:cpus", nps)

    nd = config.get("machine:device_count")
    ndt = setdefault(args, "devices_per_test", None)
    nds = setdefault(args, "devices_per_session", None)
    if ndt is not None:
        if ndt > nd:
            _die("test:devices", ndt, "machine:device_count", nd)
    if nds is not None:
        if nds > nd:
            _die("session:devices", nds, "machine:device_count", nd)
        if ndt is not None and ndt > nds:
            _die("test:devices", ndt, "session:devices", nds)

    nw = setdefault(args, "workers_per_session", None)
    if nw is not None:
        if nw > np:
            _die("session:workers", nw, "machine:cpu_count", np)
        if nps is not None and nw > nps:
            _die("session:workers", nw, "session:cpus", nps)

    bc = setdefault(args, "batch_count", None)
    bt = setdefault(args, "batch_time", None)
    if bc is not None and bt is not None:
        opt1, opt2 = f"-l batch:time:{bt}", f"-l batch:count:{bc}"
        raise ValueError(f"{opt1!r} and {opt2!r} are mutually exclusive")


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
            raise ResourceError(self, path, f"invalid scope {scope!r} (expected session)")
        if type == "time":
            value = time_in_seconds(string)
        else:
            try:
                value = int(string)
            except ValueError:
                raise ResourceError(self, path, f"invalid int {string!r}")
        return scope, type, value


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
