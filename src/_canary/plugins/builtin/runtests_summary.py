# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import random

from ... import config
from ...status import Status
from ...test.case import TestCase
from ...third_party.color import colorize
from ...util import glyphs
from ...util import logging
from ...util.time import hhmmss
from ..hookspec import hookimpl


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
def print_testcase_durations(
    cases: list[TestCase], include_pass: bool, truncate: int, N: int | None = None
) -> None:
    if N is None:
        N = config.getoption("durations")
    if N:
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


@hookimpl(specname="canary_runtests_summary", trylast=True)
def print_runtest_footer(
    cases: list[TestCase], include_pass: bool, truncate: int, title: str | None = None
) -> None:
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
        "title": title or "Session done",
    }
    string.write(colorize("%(x)s%(x)s @*{%(title)s} -- %(s)s in @*{%(t)s}\n" % kwds))
    logging.emit(string.getvalue())
