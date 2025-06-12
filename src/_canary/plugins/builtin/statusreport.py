import io
import os
from typing import TYPE_CHECKING

from ...status import Status
from ...test.case import TestCase
from ...util import logging
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...session import Session


@hookimpl(specname="canary_statusreport", tryfirst=True)
def runtest_report_status(
    session: "Session",
    report_chars: str,
    sortby: str | None,
    durations: int | None,
    pathspec: str | None,
) -> None:
    cases_to_show = determine_cases_to_show(session, report_chars, pathspec)
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


@hookimpl(specname="canary_statusreport", trylast=True)
def runtest_report_footer(
    session: "Session",
    report_chars: str,
    sortby: str | None,
    durations: int | None,
    pathspec: str | None,
) -> None:
    """Return a short, high-level, summary of test results"""
    from .runtests_summary import print_runtest_footer

    cases = session.active_cases()
    print_runtest_footer(cases, True, -1, title="Summary")


@hookimpl(specname="canary_statusreport")
def print_testcase_durations(
    session: "Session",
    report_chars: str,
    sortby: str | None,
    durations: int | None,
    pathspec: str | None,
) -> None:
    from .runtests_summary import print_testcase_durations as _print_testcase_durations

    if durations:
        _print_testcase_durations(session.active_cases(), True, -1, N=durations)


def sort_cases_by(cases: list[TestCase], field="duration") -> list[TestCase]:
    if cases and isinstance(getattr(cases[0], field), str):
        return sorted(cases, key=lambda case: getattr(case, field).lower())
    return sorted(cases, key=lambda case: getattr(case, field))


def determine_cases_to_show(
    session: "Session", report_chars: str, pathspec: str | None
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
