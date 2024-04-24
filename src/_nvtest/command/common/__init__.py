import argparse
import os
from typing import TYPE_CHECKING
from typing import Union

import _nvtest.config as config
from _nvtest.third_party.color import colorize
from _nvtest.util.time import time_in_seconds

if TYPE_CHECKING:
    from _nvtest.config.argparsing import Parser
    from _nvtest.test.case import TestCase


def setdefault(obj, attr, default):
    if not hasattr(obj, attr):
        setattr(obj, attr, default)
    return getattr(obj, attr)


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
    help_str = (
        "Defines resources that are required by the test session and "
        "establishes limits to the amount of resources that can be consumed. "
        "The resource argument is of the form: [scope:]type:value, where scope "
        "(optional) is one of session, test, or batch, (session is assumed if not provided); "
        "type is one of workers, cpus, or devices; and value is the value. See -H resources "
        "for more help and examples."
    )
    group.add_argument(
        "-l", action=ResourceSetter, metavar="resource", default=None, help=help_str
    )


def set_default_resource_args(args: argparse.Namespace) -> None:
    def _die(name1, n1, name2, n2):
        raise ValueError("'-l {0}:{1}' must not exceed {2}:{3}".format(name1, n1, name2, n2))

    setdefault(args, "test_timeout", None)
    setdefault(args, "test_timeoutx", 1.0)
    setdefault(args, "cpus_per_test", None)
    setdefault(args, "devices_per_test", None)

    setdefault(args, "session_timeout", None)
    setdefault(args, "cpus_per_session", None)
    setdefault(args, "devices_per_session", None)
    setdefault(args, "workers_per_session", None)

    setdefault(args, "batch_count", None)
    setdefault(args, "batch_time", None)
    setdefault(args, "workers_per_batch", None)

    np = config.get("machine:cpu_count")
    npt = args.cpus_per_test
    nps = args.cpus_per_session
    if npt is not None:
        if npt > np:
            _die("test:cpus", npt, "machine:cpu_count", np)
    if nps is not None:
        if nps > np:
            _die("session:cpus", nps, "machine:cpu_count", np)
        if npt is not None and npt > nps:
            _die("test:cpus", npt, "session:cpus", nps)

    nd = config.get("machine:device_count")
    ndt = args.devices_per_test
    nds = args.devices_per_session
    if ndt is not None:
        if ndt > nd:
            _die("test:devices", ndt, "machine:device_count", nd)
    if nds is not None:
        if nds > nd:
            _die("session:devices", nds, "machine:device_count", nd)
        if ndt is not None and ndt > nds:
            _die("test:devices", ndt, "session:devices", nds)

    nw = args.workers_per_session
    if nw is not None:
        if nw > np:
            _die("session:workers", nw, "machine:cpu_count", np)
        if nps is not None and nw > nps:
            _die("session:workers", nw, "session:cpus", nps)

    bc = args.batch_count
    bt = args.batch_time
    if bc is not None and bt is not None:
        opt1, opt2 = f"-l batch:time:{bt}", f"-l batch:count:{bc}"
        raise ValueError(f"{opt1!r} and {opt2!r} are mutually exclusive")


class ResourceSetter(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        scope, type, value = self.parse_path(values)
        self.set_resource_args(args, scope, type, value)

    def set_resource_args(self, args, scope, type, value):
        if scope == "batch":
            conflicting_type = "time" if type == "count" else "count"
            if hasattr(args, f"batch_{conflicting_type}"):
                raise ValueError("batch:count and batch:time are mutually exclusive")
        if type in ("workers", "cpus", "devices"):
            setattr(args, f"{type}_per_{scope}", value)
        else:
            setattr(args, f"{scope}_{type}", value)

    @staticmethod
    def type_map(type: str) -> str:
        return {"cores": "cpus", "processors": "cpus", "gpus": "devices"}.get(type, type)

    def parse_path(self, path):
        components = [_.strip() for _ in path.split(":") if _.split()]
        if len(components) == 2:
            components.insert(0, "session")
        elif len(components) != 3:
            raise ResourceError(self, path, "invalid resource spec")
        scope, arg_type, string = components
        type = self.type_map(arg_type)
        if scope in ("session", "test"):
            if type not in ("cpus", "devices", "workers", "timeout", "timeoutx"):
                raise ResourceError(self, path, f"invalid type {arg_type!r}")
        elif scope == "batch":
            if type not in ("count", "time", "workers"):
                raise ResourceError(self, path, f"invalid type {type!r}")
        else:
            raise ResourceError(self, path, f"invalid scope {scope!r}")
        if type == "workers" and scope not in ("session", "batch"):
            raise ResourceError(self, path, f"invalid scope {scope!r} (expected session)")
        if type in ("time", "timeout"):
            value = time_in_seconds(string, negatives=True if type == "timeout" else False)
        elif type == "timeoutx":
            try:
                value = float(string)
            except ValueError:
                raise ResourceError(self, path, f"invalid float {string!r}")
        else:
            try:
                value = int(string)
            except ValueError:
                raise ResourceError(self, path, f"invalid int {string!r}")
        return scope, type, value

    @staticmethod
    def help_page() -> str:
        def bold(arg: str) -> str:
            return colorize("@*{%s}" % arg)

        resource_help = """\
%(title)s

The %(r_arg)s argument is of the form: %(r_form)s, where %(r_scope)s
(optional) is one of session, test, or batch, (session is assumed if not provided);
%(r_type)s is one of workers, cpus, devices, time; and %(r_value)s is an integer or float value.

%(examples)s
• -l session:workers:N: Execute the test session asynchronously using a pool of at most N workers
• -l session:cpus:N: Occupy at most N cpu cores at any one time.
• -l session:devices:N: Occupy at most N devices at any one time.
• -l session:timeout:T: Set a timeout on test session execution in seconds (accepts human
     readable expressions like 1s, 1 hr, 2 hrs, etc) [default: 60 min]
• -l test:cpus:N: Skip tests requiring more than N cpu cores.
• -l test:devices:N: Skip tests requiring more than N devices.
• -l test:timeout:T: Set a timeout on any single test execution in seconds (accepts human
     readable expressions like 1s, 1 hr, 2 hrs, etc) [default: None]
• -l test:timeoutx:T: Multiply test timeouts by this much [default: 1.0]
• -l batch:workers:N: Execute the batch asynchronously using a pool of at most N workers
     [default: 5]
• -l batch:count:N: Execute tests in N batches.
• -l batch:time:N': Execute tests in batches having runtimes of approximately N seconds.
     [default: 30 min]
""" % {
            "title": bold("Setting limits on resources"),
            "r_form": bold("[scope:]type:value"),
            "r_arg": bold("-l resource"),
            "r_scope": bold("scope"),
            "r_type": bold("type"),
            "r_value": bold("value"),
            "examples": bold("Examples"),
        }
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
