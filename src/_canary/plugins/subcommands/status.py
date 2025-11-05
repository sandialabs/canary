# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import io
import itertools
import re
from typing import TYPE_CHECKING

from ... import status
from ...third_party import colify
from ...third_party.color import clen
from ...third_party.color import colorize
from ...util import glyphs
from ...util import logging
from ...workspace import Workspace
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Status())


class Status(CanarySubcommand):
    name = "status"
    description = "Print information about a test run"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument(
            "--durations",
            nargs="?",
            type=int,
            const=10,
            metavar="N",
            help="Show N slowest test durations (N<0 for all) [default: 10]",
        )
        parser.add_argument(
            "-o",
            "--format",
            dest="format_cols",
            default="ID,Name,Name,Session,Exit Code,Duration,Status,Details",
            action=StatusFormatAction,
            help="Change the format printed to the screen. [default: %(default)s]",
        )
        parser.add_argument(
            "-r",
            dest="report_chars",
            action=ReportCharAction,
            default="dftns",
            metavar="char",
            help="Show test summary info as specified by chars: "
            "(p)assed, "
            "(t)imeout "
            "(d)iffed, "
            "(f)ailed, "
            "(n)ot run, "
            "(s)kipped, "
            "(a)ll (except passed), "
            "(A)ll.  [default: dftns]",
        )
        parser.add_argument(
            "--sort-by",
            default="name",
            choices=("duration", "name"),
            help="Sort cases by this field [default: %(default)s]",
        )
        parser.add_argument(
            "--dump", action="store_true", help="Dump test cases to lock lock file [default: False]"
        )
        parser.add_argument("pathspec", nargs="?", help="Limit status results to this path")

    def execute(self, args: "argparse.Namespace") -> int:
        workspace = Workspace.load()
        info = workspace.statusinfo()
        table = self.get_status_table(info, args)
        fh = io.StringIO()
        colify.colify_table(table, output=fh)
        print(fh.getvalue())
        if args.durations:
            print_durations(info, N=args.durations)
        return 0

    def get_status_table(
        self, info: dict[str, list], args: "argparse.Namespace"
    ) -> list[list[str]]:
        sorted_info = sortby_status(info)
        filtered_info = filter_by_status(sorted_info, args.report_chars)
        cols = args.format_cols.split(",")
        map: dict[str, str] = {
            "ID": "id",
            "Name": "name",
            "FullName": "fullname",
            "Session": "session",
            "Exit Code": "returncode",
            "Duration": "duration",
            "Status": "status_value",
            "Details": "status_details",
        }
        nrows = len(filtered_info["id"])
        table: list[list[str]] = []
        widths = [len(_) for _ in cols]
        for i in range(nrows):
            row: list[str] = []
            for j, name in enumerate(cols):
                key = map[name]
                value = filtered_info[key][i]
                if name == "ID":
                    value = colorize("@*b{%s}" % value)
                elif name == "Name":
                    value = pretty_test_name(value)
                elif name == "Duration":
                    value = colorize("@*{%s}" % dformat(value))
                elif name == "Status":
                    value = pretty_status_name(value)
                else:
                    value = str(value)
                widths[j] = max(widths[j], clen(value))
                row.append(value)
            table.append(row)
        hlines: list[str] = ["=" * width for width in widths]
        table.insert(0, cols)
        table.insert(1, hlines)
        return table


def pretty_test_name(name: str) -> str:
    colors = itertools.cycle("bmgycr")
    if match := re.search(r"(\w+)\[(.*)\]", name):
        stem = match.group(1)
        params = match.group(2).split(",")
        string = ",".join("@%s{%s}" % (next(colors), p) for p in params)
        return colorize("%s[%s]" % (stem, string))
    return name


def pretty_status_name(name: str) -> str:
    color: str = ""
    fmt: str = "%(name)s"
    if name in ("created", "retry", "pending", "ready", "skipped"):
        color = status.Status.colors[name]
        fmt = "@*c{not run} (@*%(color)s{%(name)s})"
    elif name in ("not_run",):
        color = status.Status.colors[name]
        fmt = "@*%(color)s{not run} (failed dependency)"
    elif name in ("diffed", "failed", "timeout", "invalid", "unknown"):
        color = status.Status.colors[name]
        fmt = "@*r{failed} (@*%(color)s{%(name)s})"
    else:
        color = status.Status.colors[name]
        fmt = "@*%(color)s{%(name)s}"
    return colorize(fmt % {"color": color, "name": name})


class ReportCharAction(argparse.Action):
    chars = "pftdfnsxaA"

    def __call__(self, parser, args, values, option_string=None):
        for value in values:
            if value not in self.chars:
                parser.error(f"Invalid report char {value!r}, choose any from {self.chars!r}")
        setattr(args, self.dest, values)


class StatusFormatAction(argparse.Action):
    _choices: list[str] = [
        "ID",
        "FullName",
        "Name",
        "Session",
        "Exit Code",
        "Duration",
        "Status",
        "Details",
    ]

    def __call__(self, parser, namespace, value, option_string=None):
        items = value.split(",")
        for item in items:
            if item not in self._choices:
                choices = ",".join(self._choices)
                parser.error(f"Invalid status format {item!r}, choose any from {choices}")
        setattr(namespace, self.dest, value)


def sortby_status(info: dict[str, list]) -> dict[str, list]:
    map = {
        "invalid": 0,
        "created": 0,
        "retry": 0,
        "pending": 0,
        "ready": 0,
        "running": 0,
        "success": 10,
        "xfail": 11,
        "xdiff": 12,
        "cancelled": 20,
        "skipped": 21,
        "not_run": 22,
        "timeout": 23,
        "diffed": 30,
        "failed": 31,
        "unknown": 40,
    }
    status = info["status_value"]
    ix = sorted(range(len(status)), key=lambda n: map.get(status[n], 50))
    d: dict[str, list] = {}
    for key, value in info.items():
        d[key] = [value[i] for i in ix]
    return d


def sortby_duration(info: dict[str, list]) -> dict[str, list]:
    durations = info["duration"]
    ix = sorted(range(len(durations)), key=lambda x: -1 if x in ("NA", None) else x)
    d: dict[str, list] = {}
    for key, value in info.items():
        d[key] = [value[i] for i in ix]
    return d


def filter_by_status(info: dict[str, list], chars: str | None) -> dict[str, list]:
    chars = chars or "dftns"
    if "A" in chars:
        return info
    mask = [False] * len(info["status_value"])
    for i, stat in enumerate(info["status_value"]):
        if info["session"][i] is None:
            continue
        elif "a" in chars:
            mask[i] = stat != "success"
        elif stat == "skipped":
            mask[i] = "s" in chars
        elif stat in ("success", "xdiff", "xfail"):
            mask[i] = "p" in chars
        elif stat == "failed":
            mask[i] = "f" in chars
        elif stat == "diffed":
            mask[i] = "d" in chars
        elif stat == "timeout":
            mask[i] = "t" in chars
        elif stat == "invalid":
            mask[i] = "n" in chars
        elif stat in ("ready", "created", "pending", "cancelled", "not_run"):
            mask[i] = "n" in chars
        else:
            logger.warning(f"Unhandled status {stat}")
    filtered: dict[str, list] = {}
    for key, value in info.items():
        filtered[key] = [value[i] for i, m in enumerate(mask) if m]
    return filtered


def print_durations(info: dict, N: int) -> None:
    sorted_info = sortby_duration(info)
    fh = io.StringIO()
    ix = list(range(len(sorted_info["duration"])))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fh.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = sorted_info["duration"][i]
        if duration < 0:
            continue
        name = sorted_info["name"][i]
        id = sorted_info["id"][i]
        fh.write("  %6.2f   %s %s\n" % (duration, id, name))
    fh.write("\n")
    print(fh.getvalue())


def dformat(arg: float) -> str:
    return "NA" if arg < 0 else f"{arg:.02f}"
