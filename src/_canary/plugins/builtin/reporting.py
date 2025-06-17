# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import os
import random
from textwrap import indent
from typing import TYPE_CHECKING

from ... import config
from ...status import Status
from ...test.case import TestCase
from ...third_party.color import ccenter
from ...third_party.color import colorize
from ...util import glyphs
from ...util import logging
from ...util.string import pluralize
from ...util.term import terminal_size
from ...util.time import hhmmss
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...session import Session
    from ...test.case import TestCase


@hookimpl(specname="canary_runtests_summary", tryfirst=True)
def print_short_test_status_summary(
    cases: list[TestCase], include_pass: bool, truncate: int
) -> None:
    """Return a summary of the completed test cases.  if ``include_pass is True``, include
    passed tests in the summary

    """
    if config.getoption("no_summary"):
        return
    file = io.StringIO()
    if not cases:
        file.write("Nothing to report\n")
    else:
        totals: dict[str, list[TestCase]] = {}
        for case in cases:
            totals.setdefault(case.status.value, []).append(case)
        for status in Status.members:
            if not include_pass and status == "success":
                continue
            glyph = Status.glyph(status)
            if status in totals:
                n: int = 0
                for case in sorted(totals[status], key=lambda t: t.name):
                    file.write("%s %s\n" % (glyph, case.describe()))
                    n += 1
                    if truncate > 0 and truncate == n:
                        cname = case.status.cname
                        bullets = colorize("@*{%s}" % (3 * "."))
                        fmt = "%s %s %s truncating summary to the first %d entries. "
                        alert = io.StringIO()
                        alert.write(fmt % (glyph, cname, bullets, truncate))
                        alert.write(colorize("See @*{canary status} for the full summary\n"))
                        file.write(alert.getvalue())
                        break
    string = file.getvalue()
    if string.strip():
        string = colorize("@*{Short test summary info}\n") + string + "\n"
    logging.emit(string)


@hookimpl(specname="canary_runtests_summary")
def print_runtests_durations(cases: list[TestCase], include_pass: bool, truncate: int) -> None:
    if N := config.getoption("durations"):
        return print_durations(cases, N)


@hookimpl(specname="canary_statusreport")
def print_statusreport_durations(session: "Session") -> None:
    if N := config.getoption("durations"):
        print_durations(session.active_cases(), N)


@hookimpl(specname="canary_runtests_summary", trylast=True)
def runtests_footer(
    cases: list[TestCase], include_pass: bool, truncate: int, title: str | None = None
) -> None:
    """Return a short, high-level, summary of test results"""
    print_footer(cases, "Session done")


@hookimpl(specname="canary_statusreport", trylast=True)
def status_footer(session: "Session") -> None:
    """Return a short, high-level, summary of test results"""
    cases = session.active_cases()
    print_footer(cases, "Summary")


@hookimpl(specname="canary_statusreport", tryfirst=True)
def runtest_report_status(session: "Session") -> None:
    report_chars = config.getoption("report_chars") or "dftns"
    sortby = config.getoption("sort_by", "duration")
    cases_to_show = determine_cases_to_show(session, report_chars)
    if cases_to_show:
        file = io.StringIO()
        totals: dict[str, list[TestCase]] = {}
        for case in cases_to_show:
            totals.setdefault(case.status.value, []).append(case)
        for member in Status.members:
            if member in totals:
                for case in sort_cases_by(totals[member], field=sortby or "duration"):
                    glyph = Status.glyph(case.status.value)
                    description = case.describe()
                    file.write("%s %s\n" % (glyph, description))
        file.write("\n")
        logging.emit(file.getvalue())


@hookimpl
def canary_collectreport(cases: list["TestCase"]) -> None:
    excluded: list[TestCase] = []
    for case in cases:
        if case.wont_run():
            excluded.append(case)
    n = len(cases) - len(excluded)
    logging.info(colorize("@*{Selected} %d test %s" % (n, pluralize("case", n))))
    if excluded:
        n = len(excluded)
        logging.info(colorize("@*{Excluding} %d test cases for the following reasons:" % n))
        reasons: dict[str | None, int] = {}
        for case in excluded:
            if case.status.satisfies(("masked", "invalid")):
                reasons[case.status.details] = reasons.get(case.status.details, 0) + 1
        keys = sorted(reasons, key=lambda x: reasons[x])
        for key in reversed(keys):
            reason = key if key is None else key.lstrip()
            logging.emit(f"{3 * glyphs.bullet} {reasons[key]}: {reason}\n")


def print_durations(cases: list[TestCase], N: int) -> None:
    string = io.StringIO()
    cases = [c for c in cases if c.duration >= 0]
    sorted_cases = sorted(cases, key=lambda x: x.duration)
    if N > 0:
        sorted_cases = sorted_cases[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    string.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for case in sorted_cases:
        string.write("  %6.2f   %s\n" % (case.duration, case.format("%id   %X")))
    string.write("\n")
    logging.emit(string.getvalue())


def sort_cases_by(cases: list[TestCase], field="duration") -> list[TestCase]:
    if cases and isinstance(getattr(cases[0], field), str):
        return sorted(cases, key=lambda case: getattr(case, field).lower())
    return sorted(cases, key=lambda case: getattr(case, field))


def determine_cases_to_show(
    session: "Session", report_chars: str, pathspec: str | None = None
) -> list[TestCase]:
    cases: list[TestCase] = session.cases
    cases_to_show: list[TestCase]
    rc = set(report_chars)
    if pathspec is not None:
        if TestCase.spec_like(pathspec):
            cases = [c for c in cases if c.matches(pathspec)]
            rc.add("A")
        else:
            pathspec = os.path.abspath(pathspec)
            if pathspec != session.work_tree:
                cases = [c for c in cases if c.working_directory.startswith(pathspec)]
    if "A" in rc:
        if "x" in rc:
            cases_to_show = cases
        else:
            cases_to_show = [c for c in cases if not c.masked()]
    elif "a" in rc:
        if "x" in rc:
            cases_to_show = [c for c in cases if c.status != "success"]
        else:
            cases_to_show = [c for c in cases if not c.masked() and c.status != "success"]
    else:
        cases_to_show = []
        for case in cases:
            if case.masked():
                if "x" in rc:
                    cases_to_show.append(case)
            elif "s" in rc and case.status == "skipped":
                cases_to_show.append(case)
            elif "p" in rc and case.status.value in ("success", "xdiff", "xfail"):
                cases_to_show.append(case)
            elif "f" in rc and case.status == "failed":
                cases_to_show.append(case)
            elif "d" in rc and case.status == "diffed":
                cases_to_show.append(case)
            elif "t" in rc and case.status == "timeout":
                cases_to_show.append(case)
            elif "n" in rc and case.status == "invalid":
                cases_to_show.append(case)
            elif "n" in rc and case.status.value in (
                "ready",
                "created",
                "pending",
                "cancelled",
                "not_run",
            ):
                cases_to_show.append(case)
    return cases_to_show


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    parser.add_argument(
        "--show-capture",
        command="run",
        group="console reporting",
        nargs="?",
        choices=("o", "e", "oe", "no"),
        default="no",
        const="oe",
        help="Show captured stdout (o), stderr (e), or both (oe) "
        "for failed tests [default: %(default)s]",
    )
    parser.add_argument(
        "--capture",
        command="run",
        choices=("log", "tee"),
        default="log",
        group="console reporting",
        help="Log test output to a file only (log) or log and print output "
        "to the screen (tee).  Warning: this could result in a large amount of text printed "
        "to the screen [default: log]",
    )


@hookimpl(specname="canary_session_finish", trylast=True)
def show_capture(session: "Session", exitstatus: int) -> None:
    what = config.getoption("show_capture")
    if what in ("no", None):
        return
    cases = session.active_cases()
    failed = [case for case in cases if not case.status.satisfies(("success", "xdiff", "xfail"))]
    if failed:
        _, width = terminal_size()
        print(ccenter(colorize(" @*R{%d Test failures} " % len(failed)), width, "="), end="\n\n")
        for case in failed:
            _show_capture(case, what=what)


def _show_capture(case: "TestCase", what="oe") -> None:
    _, width = terminal_size()
    color = "g" if case.status == "success" else "R" if case.status == "failed" else "y"
    fp = io.StringIO()
    fp.write(ccenter(colorize(" @*%s{%s} " % (color, case.display_name)), width, "-") + "\n")
    fp.write(f"{bold('Status')}: {case.status.cname}\n")
    fp.write(f"{bold('Execution directory')}: {case.execution_directory}\n")
    fp.write(f"{bold('Command')}: {' '.join(case.command())}\n")
    if what in ("o", "oe") and case.stdout_file:
        file = case.stdout_file
        if os.path.exists(file):
            with open(file) as fh:
                stdout = fh.read().strip()
            if stdout:
                fp.write(bold("stdout") + "\n")
                fp.write(indent(stdout, "  ") + "\n")
    if what in ("e", "oe") and case.stderr_file:
        file = case.stderr_file
        if os.path.exists(file):
            with open(file) as fh:
                stderr = fh.read().strip()
            if stderr:
                fp.write(bold("stderr") + "\n")
                fp.write(indent(stderr, "  ") + "\n")
    text = fp.getvalue()
    if text.strip():
        print(text)


def print_footer(cases: list[TestCase], title: str) -> None:
    """Return a short, high-level, summary of test results"""
    string = io.StringIO()
    duration = -1.0
    has_a = any(_.start for _ in cases if _.start > 0)
    has_b = any(_.stop for _ in cases if _.stop > 0)
    if has_a and has_b:
        finish = max(_.stop for _ in cases if _.stop > 0)
        start = min(_.start for _ in cases if _.start > 0)
        duration = finish - start
    totals: dict[str, list[TestCase]] = {}
    for case in cases:
        totals.setdefault(case.status.value, []).append(case)
    N = len(cases)
    summary = ["@*b{%d total}" % N]
    for member in Status.colors:
        n = len(totals.get(member, []))
        if n:
            c = Status.colors[member]
            stat = totals[member][0].status.name
            summary.append(colorize("@%s{%d %s}" % (c, n, stat.lower())))
    emojis = [glyphs.sparkles, glyphs.collision, glyphs.highvolt]
    x, y = random.sample(emojis, 2)
    kwds = {
        "x": x,
        "y": y,
        "s": ", ".join(summary),
        "t": hhmmss(None if duration < 0 else duration),
        "title": title,
    }
    string.write(colorize("%(x)s%(x)s @*{%(title)s} -- %(s)s in @*{%(t)s}\n" % kwds))
    logging.emit(string.getvalue())


def bold(string: str) -> str:
    return colorize("@*{%s}" % string)
