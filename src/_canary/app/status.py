# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Programming interface for inspecting Canary status results.

This module provides a semantic, JSON-serializable status API for programs,
notebooks, dashboards, MCP tools, and agents.

It intentionally does not expose the command-line ``canary status`` report-char
interface.  Use functions such as ``failed()``, ``running()``, ``summary()``,
and ``snapshot()`` instead.
"""

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import Literal

from _canary.workspace.workspace import Workspace

from .query_helpers import row_to_job_entry

_FAILED_OUTCOMES = {"FAILED", "ERROR", "BROKEN"}
SortBy = Literal["name", "duration", "status", "session"]


def jobs(
    *,
    category: str | None = None,
    outcome: str | None = None,
    passed: bool | None = None,
    failed: bool | None = None,
    running: bool | None = None,
    done: bool | None = None,
    session: str | None = None,
    name_contains: str | None = None,
    full_ids: bool = True,
    sort_by: SortBy = "name",
    reverse: bool = False,
) -> list[dict[str, Any]]:
    """Return current workspace job status entries.

    Args:
        category: Optional status category filter, e.g. ``"PASS"``,
            ``"FAIL"``, ``"SKIP"``, ``"CANCEL"``, or ``"NONE"``.
        outcome: Optional status outcome filter, e.g. ``"PASSED"``,
            ``"FAILED"``, ``"TIMEOUT"``, or ``"DIFFED"``.
        passed: If true, only successful jobs.  If false, only non-successful
            jobs.
        failed: If true, only failure-category jobs.  If false, only jobs that
            are not failure-category jobs.
        running: If true, only currently running jobs.  If false, only jobs not
            currently running.
        done: If true, only completed jobs.  If false, only incomplete jobs.
        session: Optional exact session-name filter.
        name_contains: Optional case-insensitive substring filter against the
            job name and full name.
        full_ids: If false, ``id`` is shortened to 7 characters.  ``full_id`` is
            always present.
        sort_by: Sort key: ``"name"``, ``"duration"``, ``"status"``, or
            ``"session"``.
        reverse: Reverse the chosen sort order.

    Returns:
        A list of JSON-serializable job dictionaries.
    """

    entries = _entries(full_ids=full_ids)
    entries = _filter_entries(
        entries,
        category=category,
        outcome=outcome,
        passed=passed,
        failed=failed,
        running=running,
        done=done,
        session=session,
        name_contains=name_contains,
    )
    entries.sort(key=_sort_key(sort_by), reverse=reverse)
    return entries


def summary() -> dict[str, Any]:
    """Return summary counts for the current workspace status."""

    entries = _entries(full_ids=True)

    counts = {
        "total": len(entries),
        "passed": 0,
        "failed": 0,
        "diffed": 0,
        "timeout": 0,
        "skipped": 0,
        "cancelled": 0,
        "running": 0,
        "not_run": 0,
        "nonpassing": 0,
        "other": 0,
    }

    for entry in entries:
        if entry["passed"]:
            counts["passed"] += 1
        else:
            counts["nonpassing"] += 1

        if entry["running"]:
            counts["running"] += 1

        if entry["not_run"]:
            counts["not_run"] += 1

        if entry["failed"]:
            counts["failed"] += 1
        elif entry["diffed"]:
            counts["diffed"] += 1
        elif entry["timeout"]:
            counts["timeout"] += 1
        elif entry["skipped"]:
            counts["skipped"] += 1
        elif entry["cancelled"]:
            counts["cancelled"] += 1
        elif not entry["passed"] and not entry["running"] and not entry["not_run"]:
            counts["other"] += 1

    return {**counts, "ok": counts["total"] > 0 and counts["passed"] == counts["total"]}


def snapshot(*, include_jobs: bool = True, full_ids: bool = True) -> dict[str, Any]:
    """Return a complete status snapshot for the current workspace.

    Args:
        include_jobs: Include per-job status entries.
        full_ids: If false, per-job ``id`` values are shortened to 7
            characters.  ``full_id`` remains available.

    Returns:
        A JSON-serializable snapshot containing summary counts and useful job
        subsets.
    """

    entries = jobs(full_ids=full_ids) if include_jobs else []
    s = summary()

    report: dict[str, Any] = {"ok": s["ok"], "summary": s}

    if include_jobs:
        report.update(
            {
                "jobs": entries,
                "failed": [entry for entry in entries if entry["failed"]],
                "nonpassing": [entry for entry in entries if not entry["passed"]],
                "running": [entry for entry in entries if entry["running"]],
                "not_run": [entry for entry in entries if entry["not_run"]],
            }
        )

    return report


def ok() -> bool:
    """Return true if the current workspace has jobs and all jobs passed."""

    return bool(summary()["ok"])


def passed(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return successful jobs."""

    return jobs(passed=True, full_ids=full_ids, sort_by=sort_by)


def failed(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return failure-category jobs.

    This includes jobs whose status category is ``FAIL`` or whose status object
    reports ``is_failure()``.
    """

    return jobs(failed=True, full_ids=full_ids, sort_by=sort_by)


def nonpassing(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return jobs that did not pass.

    This includes failed, diffed, timed-out, skipped, cancelled, running, and
    not-run jobs.
    """

    return jobs(passed=False, full_ids=full_ids, sort_by=sort_by)


def running(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return currently running jobs."""

    return jobs(running=True, full_ids=full_ids, sort_by=sort_by)


def not_run(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return jobs that have not completed and are not currently running."""

    return [entry for entry in jobs(full_ids=full_ids, sort_by=sort_by) if entry["not_run"]]


def skipped(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return skipped jobs."""

    return [entry for entry in jobs(full_ids=full_ids, sort_by=sort_by) if entry["skipped"]]


def cancelled(*, full_ids: bool = True, sort_by: SortBy = "name") -> list[dict[str, Any]]:
    """Return cancelled jobs."""

    return [entry for entry in jobs(full_ids=full_ids, sort_by=sort_by) if entry["cancelled"]]


def by_category(
    category: str, *, full_ids: bool = True, sort_by: SortBy = "name"
) -> list[dict[str, Any]]:
    """Return jobs matching a status category."""

    return jobs(category=category, full_ids=full_ids, sort_by=sort_by)


def by_outcome(
    outcome: str, *, full_ids: bool = True, sort_by: SortBy = "name"
) -> list[dict[str, Any]]:
    """Return jobs matching a status outcome."""

    return jobs(outcome=outcome, full_ids=full_ids, sort_by=sort_by)


def slowest(
    n: int = 10, *, include_incomplete: bool = False, full_ids: bool = True
) -> list[dict[str, Any]]:
    """Return the slowest jobs by measured duration.

    Args:
        n: Number of jobs to return.  If negative, return all matching jobs.
        include_incomplete: Include jobs whose duration is unavailable.
        full_ids: If false, ``id`` is shortened to 7 characters.

    Returns:
        Jobs sorted from slowest to fastest.
    """

    entries = jobs(full_ids=full_ids)
    if not include_incomplete:
        entries = [entry for entry in entries if _duration(entry) >= 0]

    entries.sort(key=_duration, reverse=True)

    if n < 0:
        return entries
    return entries[:n]


def raw_results() -> dict[str, Any]:
    """Return the latest result record for each spec in the current workspace."""

    return Workspace.load().db.get_results()


def _entries(*, full_ids: bool) -> list[dict[str, Any]]:
    workspace = Workspace.load()
    cache: dict = {}
    return [
        _row_to_entry(workspace, row, full_ids=full_ids, cache=cache)
        for row in raw_results().values()
    ]


def _filter_entries(
    entries: list[dict[str, Any]],
    *,
    category: str | None,
    outcome: str | None,
    passed: bool | None,
    failed: bool | None,
    running: bool | None,
    done: bool | None,
    session: str | None,
    name_contains: str | None,
) -> list[dict[str, Any]]:
    if category is not None:
        wanted = category.upper()
        entries = [entry for entry in entries if entry["status"]["category"].upper() == wanted]

    if outcome is not None:
        wanted = outcome.upper()
        entries = [entry for entry in entries if entry["status"]["outcome"].upper() == wanted]

    if passed is not None:
        entries = [entry for entry in entries if entry["passed"] is passed]

    if failed is not None:
        entries = [entry for entry in entries if entry["failed"] is failed]

    if running is not None:
        entries = [entry for entry in entries if entry["running"] is running]

    if done is not None:
        entries = [entry for entry in entries if entry["done"] is done]

    if session is not None:
        entries = [entry for entry in entries if entry["session"] == session]

    if name_contains is not None:
        needle = name_contains.lower()
        entries = [
            entry
            for entry in entries
            if needle in entry["name"].lower() or needle in entry["fullname"].lower()
        ]

    return entries


def _is_failed_outcome(outcome: str) -> bool:
    return outcome.upper() in _FAILED_OUTCOMES


def _row_to_entry(
    workspace: Workspace, row: dict[str, Any], *, full_ids: bool, cache: dict | None = None
) -> dict[str, Any]:
    """The job record (:func:`row_to_job_entry`), with a short ``id`` unless *full_ids*,
    ``full_id``, and this module's booleans."""
    status = row["status"]
    state = row["state"]
    record = row_to_job_entry(workspace, row, cache, details=False)  # SQL only: stays fast

    full_id = row["id"]
    is_running = bool(_call(state, "is_running", default=False))
    is_done = bool(_call(state, "is_done", default=False))
    return {
        **record,
        "id": full_id if full_ids else full_id[:7],
        "full_id": full_id,
        "running": is_running,
        "done": is_done,
        "not_run": not is_done and not is_running,
        "passed": bool(_call(status, "is_success", default=False)),
        "failed": _is_failed_outcome(record["status"]["outcome"]),
        "skipped": bool(_call(status, "is_skipped", default=False)),
        "diffed": bool(_call(status, "is_diffed", default=False)),
        "timeout": bool(_call(status, "is_timeout", default=False)),
        "cancelled": bool(_call(status, "is_cancelled", default=False)),
    }


def _sort_key(sort_by: SortBy) -> Callable[[dict[str, Any]], Any]:
    if sort_by == "name":
        return lambda entry: entry["name"]
    if sort_by == "duration":
        return _duration
    if sort_by == "status":
        return lambda entry: (
            entry["status"]["category"],
            entry["status"]["outcome"],
            entry["name"],
        )
    if sort_by == "session":
        return lambda entry: (entry["session"], entry["name"])
    raise ValueError(f"invalid sort key {sort_by!r}")


def _duration(entry: dict[str, Any]) -> float:
    """The entry's duration, ``-1`` when unknown (the record's ``None``)."""
    duration = entry["duration"]
    return -1.0 if duration is None else float(duration)


def _call(obj: Any, name: str, *, default: Any) -> Any:
    method = getattr(obj, name, None)
    if method is None:
        return default
    return method()


__all__ = [
    "SortBy",
    "by_category",
    "by_outcome",
    "cancelled",
    "failed",
    "jobs",
    "nonpassing",
    "not_run",
    "ok",
    "passed",
    "raw_results",
    "running",
    "skipped",
    "slowest",
    "snapshot",
    "summary",
]
