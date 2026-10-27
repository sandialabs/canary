# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Semantic programming interface for querying Canary workspaces.

This module is intentionally not a one-to-one Python spelling of
``canary query``.  It provides agent/user-forward functions for common
questions about sessions, jobs, measurements, environments, and result history.

Raw lock-file JSON path queries and SQL are still available as explicit escape
hatches via ``raw_*`` and ``sql`` helpers.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any
from typing import Literal
from typing import Sequence

from _canary.api.failures import failures
from _canary.cli import query as _query_cmd
from _canary.session.workspace import Workspace
from _canary.util.query_data import query_json

SortBy = Literal["name", "status", "session", "duration"]
_MISSING = object()
_FAILED_OUTCOMES = {"FAILED", "ERROR", "BROKEN"}
_TIMEOUT_OUTCOMES = {"TIMEOUT"}
_DIFF_OUTCOMES = {"DIFFED"}
_SKIP_CATEGORIES = {"SKIP"}
_CANCEL_CATEGORIES = {"CANCEL"}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def latest_session() -> str:
    """Return the name of the latest Canary session."""

    workspace = Workspace.load()
    session_dir = _query_cmd._resolve_session_dir(workspace, "latest")
    return _session_name_from_dir(session_dir)


def session(session: str = "latest") -> dict[str, Any]:
    """Return session metadata plus summary counts.

    Args:
        session: Session name, prefix, or ``"latest"``.

    Returns:
        A JSON-serializable dictionary with session lock metadata and a
        ``summary`` field.
    """

    workspace = Workspace.load()
    session_dir = _query_cmd._resolve_session_dir(workspace, session)
    data = raw_session_lock(session, workspace=workspace)
    name = data.get("name", session_dir.name)

    return {
        "name": name,
        "started_on": data.get("started_on"),
        "finished_on": data.get("finished_on"),
        "returncode": data.get("returncode"),
        "argv": data.get("argv", []),
        "summary": session_summary(name, workspace=workspace),
    }


def sessions(
    *, returncode: int | None = None, ok: bool | None = None, name_contains: str | None = None
) -> list[dict[str, Any]]:
    """Return all known sessions with summary statistics.

    Args:
        returncode: Optional exact return-code filter.
        ok: If true, only sessions whose return code is zero.  If false, only
            sessions whose return code is nonzero or missing.
        name_contains: Optional case-insensitive session-name substring filter.
    """

    workspace = Workspace.load()
    out: list[dict[str, Any]] = []

    for session_dir in sorted(workspace.sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue

        lockfile = session_dir / "session.lock"
        if not lockfile.exists():
            continue

        data = json.loads(lockfile.read_text())
        name = data.get("name", session_dir.name)
        rc = data.get("returncode")

        entry = {
            "name": name,
            "started_on": data.get("started_on"),
            "finished_on": data.get("finished_on"),
            "returncode": rc,
            "argv": data.get("argv", []),
            "summary": session_summary(name, workspace=workspace),
        }

        if returncode is not None and rc != returncode:
            continue

        if ok is True and rc != 0:
            continue

        if ok is False and rc == 0:
            continue

        if name_contains is not None and name_contains.lower() not in name.lower():
            continue

        out.append(entry)

    return out


def session_summary(
    session: str = "latest", *, workspace: Workspace | None = None
) -> dict[str, Any]:
    """Return outcome/category counts for a session."""

    workspace = workspace or Workspace.load()
    session_dir = _query_cmd._resolve_session_dir(workspace, session)
    name = _session_name_from_dir(session_dir)

    rows = _query_cmd._db_results_for_session(workspace, name)
    entries = [_entry_from_row(workspace, row) for row in rows]

    counts = {
        "total": len(entries),
        "passed": 0,
        "failed": 0,
        "diffed": 0,
        "timeout": 0,
        "skipped": 0,
        "cancelled": 0,
        "unfinished": 0,
        "nonpassing": 0,
        "other": 0,
    }

    for entry in entries:
        if _is_passed(entry):
            counts["passed"] += 1
        else:
            counts["nonpassing"] += 1

        if _is_failed(entry):
            counts["failed"] += 1
        elif _is_diffed(entry):
            counts["diffed"] += 1
        elif _is_timeout(entry):
            counts["timeout"] += 1
        elif _is_skipped(entry):
            counts["skipped"] += 1
        elif _is_cancelled(entry):
            counts["cancelled"] += 1
        elif _is_unfinished(entry):
            counts["unfinished"] += 1
        elif not _is_passed(entry):
            counts["other"] += 1

    return {**counts, "ok": counts["total"] > 0 and counts["passed"] == counts["total"]}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def jobs(
    *,
    session: str | None = "latest",
    category: str | None = None,
    outcome: str | None = None,
    passed: bool | None = None,
    failed: bool | None = None,
    nonpassing: bool | None = None,
    unfinished: bool | None = None,
    name_contains: str | None = None,
    duration_gt: float | None = None,
    duration_lt: float | None = None,
    sort_by: SortBy = "name",
    reverse: bool = False,
) -> list[dict[str, Any]]:
    """Return job result entries.

    Args:
        session: Session name, prefix, or ``"latest"``.  Use ``None`` to query
            the latest known run of each job across all sessions.
        category: Optional status category filter, e.g. ``"PASS"`` or
            ``"FAIL"``.
        outcome: Optional status outcome filter, e.g. ``"PASSED"``,
            ``"FAILED"``, ``"TIMEOUT"``, or ``"DIFFED"``.
        passed: If true, only passed jobs.  If false, only non-passed jobs.
        failed: If true, only failed/error/broken jobs.  If false, exclude those
            jobs.
        nonpassing: If true, only jobs that did not pass.  If false, only
            passed jobs.
        unfinished: If true, only nonterminal jobs.  If false, only terminal
            jobs.
        name_contains: Optional case-insensitive substring filter against job
            name and full name.
        duration_gt: Optional lower bound on running duration.
        duration_lt: Optional upper bound on running duration.
        sort_by: Sort key: ``"name"``, ``"status"``, ``"session"``, or
            ``"duration"``.
        reverse: Reverse the chosen sort order.

    Returns:
        A list of JSON-serializable standard job entries.
    """

    workspace = Workspace.load()
    rows = _job_rows(workspace, session=session)
    entries = [_entry_from_row(workspace, row) for row in rows]

    entries = _filter_jobs(
        entries,
        category=category,
        outcome=outcome,
        passed=passed,
        failed=failed,
        nonpassing=nonpassing,
        unfinished=unfinished,
        name_contains=name_contains,
        duration_gt=duration_gt,
        duration_lt=duration_lt,
    )
    entries.sort(key=_job_sort_key(sort_by), reverse=reverse)
    return entries


def job(job_id: str) -> dict[str, Any]:
    """Return the latest known result entry for one job."""

    workspace = Workspace.load()
    found = workspace.find_job(job_id)

    history = _job_history_rows(workspace, found.id)
    if not history:
        raise ValueError(f"No run history found for job {job_id!r}")

    return _entry_from_row(workspace, history[-1])


def job_history(job_id: str) -> list[dict[str, Any]]:
    """Return all known result entries for one job across sessions.

    The order follows the database history order, which is expected to be
    oldest-to-newest.
    """

    workspace = Workspace.load()
    found = workspace.find_job(job_id)
    return [_entry_from_row(workspace, row) for row in _job_history_rows(workspace, found.id)]


def passed_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return passed jobs."""

    return jobs(session=session, passed=True)


def failed_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return failed/error/broken jobs.

    This intentionally excludes timeout and diff outcomes.  Use
    :func:`timeout_jobs` or :func:`diffed_jobs` for those.
    """

    return jobs(session=session, failed=True)


def nonpassing_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return all jobs that did not pass."""

    return jobs(session=session, nonpassing=True)


def unfinished_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return jobs whose status category is nonterminal/``NONE``."""

    return jobs(session=session, unfinished=True)


def running_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return currently unfinished jobs.

    The query database records terminal status categories.  At this level,
    ``running`` means the job is still nonterminal, i.e. category ``NONE``.
    """

    return unfinished_jobs(session=session)


def timeout_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return timed-out jobs."""

    return jobs(session=session, outcome="TIMEOUT")


def diffed_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return diffed jobs."""

    return jobs(session=session, outcome="DIFFED")


def skipped_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return skipped jobs."""

    return jobs(session=session, category="SKIP")


def cancelled_jobs(session: str | None = "latest") -> list[dict[str, Any]]:
    """Return cancelled jobs."""

    return jobs(session=session, category="CANCEL")


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def measurements(job_id: str) -> dict[str, Any]:
    """Return the measurement dictionary for a job."""

    data = raw_job_lock(job_id)
    value = data.get("measurements", {})
    return value if isinstance(value, dict) else {}


def measurement(job_id: str, key: str, default: Any = None) -> Any:
    """Return one measurement value for a job."""

    return measurements(job_id).get(key, default)


def measurement_table(
    *, session: str | None = "latest", key: str | None = None, include_status: bool = True
) -> list[dict[str, Any]]:
    """Return measurements for jobs as row-oriented data.

    Args:
        session: Session name, prefix, ``"latest"``, or ``None`` for latest
            known run of each job across all sessions.
        key: Optional measurement key.  If omitted, one row is returned per
            measurement key/value pair.
        include_status: Include job status in each row.

    Returns:
        Rows with ``id``, ``name``, ``session``, ``key``, and ``value`` fields,
        plus ``status`` when requested.
    """

    workspace = Workspace.load()
    rows = _job_rows(workspace, session=session)

    out: list[dict[str, Any]] = []
    for row in rows:
        entry = _entry_from_row(workspace, row)
        values = _measurements_from_row(row)

        if key is not None:
            if key not in values:
                continue
            items = [(key, values[key])]
        else:
            items = sorted(values.items())

        for measurement_key, value in items:
            item: dict[str, Any] = {
                "id": entry["id"],
                "name": entry["name"],
                "fullname": entry.get("fullname"),
                "session": entry["session"],
                "key": measurement_key,
                "value": value,
            }
            if include_status:
                item["status"] = entry.get("status", {})
            out.append(item)

    out.sort(key=lambda row: (row["name"], row["key"]))
    return out


# ---------------------------------------------------------------------------
# Environment, cache, and raw lock-file escape hatches
# ---------------------------------------------------------------------------


def environment(job_id: str, key: str | None = None, default: Any = None) -> Any:
    """Return a job's captured runtime environment.

    Args:
        job_id: Job ID or prefix.
        key: Optional environment variable name.
        default: Value returned when ``key`` is requested but missing.
    """

    workspace = Workspace.load()
    lockfile = _query_cmd._job_lockfile(workspace, job_id)
    env_file = Path(lockfile).parent / "env.json"

    if not env_file.exists():
        raise FileNotFoundError(env_file)

    data = json.loads(env_file.read_text())
    if key is None:
        return data
    return data.get(key, default)


def cache(job_id: str) -> dict[str, Any]:
    """Return the per-job timing cache for a job."""

    workspace = Workspace.load()
    found = workspace.find_job(job_id)
    path = _query_cmd._find_cache_path(found)
    if path is None:
        raise FileNotFoundError(f"No cache entry found for job {job_id!r}")
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, dict) else {"value": data}


def raw_job_lock(job_id: str, *, workspace: Workspace | None = None) -> dict[str, Any]:
    """Return a job's raw ``testcase.lock`` document."""

    workspace = workspace or Workspace.load()
    lockfile = _query_cmd._job_lockfile(workspace, job_id)
    return json.loads(Path(lockfile).read_text())


def raw_session_lock(
    session: str = "latest", *, workspace: Workspace | None = None
) -> dict[str, Any]:
    """Return a session's raw ``session.lock`` document."""

    workspace = workspace or Workspace.load()
    session_dir = _query_cmd._resolve_session_dir(workspace, session)
    lockfile = session_dir / "session.lock"
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    return json.loads(lockfile.read_text())


def raw_job_value(
    job_id: str, path: str = ".", *, default: Any = _MISSING, clean: bool = True
) -> Any:
    """Query a value from a job's raw ``testcase.lock`` document."""

    data = raw_job_lock(job_id)
    normalized_path = _normalize_json_path(path)

    try:
        value = query_json(data, normalized_path)
    except Exception:
        if default is _MISSING:
            raise
        return default

    return _query_cmd._clean(value) if clean else value


def raw_session_value(
    session: str = "latest", path: str = ".", *, default: Any = _MISSING, clean: bool = True
) -> Any:
    """Query a value from a session's raw ``session.lock`` document."""

    data = raw_session_lock(session)
    normalized_path = _normalize_json_path(path)

    try:
        value = query_json(data, normalized_path)
    except Exception:
        if default is _MISSING:
            raise
        return default

    return _query_cmd._clean(value) if clean else value


def raw_job_keys(job_id: str, path: str = ".") -> list[str]:
    """Return immediate keys under a raw job-lock JSON path.

    Unlike ``list_json_object_paths()``, this returns scalar-valued keys too.
    """

    return _raw_keys(raw_job_lock(job_id), path)


def raw_session_keys(session: str = "latest", path: str = ".") -> list[str]:
    """Return immediate keys under a raw session-lock JSON path.

    Unlike ``list_json_object_paths()``, this returns scalar-valued keys too.
    """

    return _raw_keys(raw_session_lock(session), path)


# ---------------------------------------------------------------------------
# Database escape hatches
# ---------------------------------------------------------------------------


def db_schema() -> Any:
    """Return workspace database schema information."""

    workspace = Workspace.load()
    return workspace.db.get_schema()


def db_stats() -> Any:
    """Return workspace database statistics."""

    workspace = Workspace.load()
    return workspace.db.get_stats()


def sql(statement: str | Sequence[str]) -> list[dict[str, Any]]:
    """Execute a read-only SQL SELECT against the workspace database."""

    workspace = Workspace.load()
    query = _sql_string(statement)

    try:
        return workspace.db.select(query)
    except ValueError as exc:
        raise ValueError("query.sql only permits SELECT statements") from exc
    except sqlite3.Error:
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _job_rows(workspace: Workspace, *, session: str | None) -> list[dict[str, Any]]:
    if session is not None:
        session_dir = _query_cmd._resolve_session_dir(workspace, session)
        session_name = _session_name_from_dir(session_dir)
        rows = _query_cmd._db_results_for_session(workspace, session_name)
        return list(rows)

    workspace.db.connect()
    try:
        result_map = workspace.db.get_results()
    finally:
        workspace.db.close()

    rows = list(result_map.values())
    rows.sort(key=lambda row: row.get("spec_name", ""))
    return rows


def _job_history_rows(workspace: Workspace, job_id: str) -> list[dict[str, Any]]:
    workspace.db.connect()
    try:
        return list(workspace.db.get_result_history(job_id))
    finally:
        workspace.db.close()


def _entry_from_row(workspace: Workspace, row: dict[str, Any]) -> dict[str, Any]:
    entry = _query_cmd._row_to_job_entry(workspace, row)

    # Add a few booleans that are useful to agents/scripts without changing the
    # standard CLI job-entry shape.
    entry["passed"] = _is_passed(entry)
    entry["failed"] = _is_failed(entry)
    entry["diffed"] = _is_diffed(entry)
    entry["timeout"] = _is_timeout(entry)
    entry["skipped"] = _is_skipped(entry)
    entry["cancelled"] = _is_cancelled(entry)
    entry["unfinished"] = _is_unfinished(entry)
    entry["nonpassing"] = not entry["passed"]
    entry["duration"] = _duration(entry)

    return entry


def _filter_jobs(
    entries: list[dict[str, Any]],
    *,
    category: str | None,
    outcome: str | None,
    passed: bool | None,
    failed: bool | None,
    nonpassing: bool | None,
    unfinished: bool | None,
    name_contains: str | None,
    duration_gt: float | None,
    duration_lt: float | None,
) -> list[dict[str, Any]]:
    if category is not None:
        wanted = category.upper()
        entries = [entry for entry in entries if _category(entry) == wanted]

    if outcome is not None:
        wanted = outcome.upper()
        entries = [entry for entry in entries if _outcome(entry) == wanted]

    if passed is not None:
        entries = [entry for entry in entries if entry["passed"] is passed]

    if failed is not None:
        entries = [entry for entry in entries if entry["failed"] is failed]

    if nonpassing is not None:
        entries = [entry for entry in entries if entry["nonpassing"] is nonpassing]

    if unfinished is not None:
        entries = [entry for entry in entries if entry["unfinished"] is unfinished]

    if name_contains is not None:
        needle = name_contains.lower()
        entries = [
            entry
            for entry in entries
            if needle in entry["name"].lower() or needle in str(entry.get("fullname", "")).lower()
        ]

    if duration_gt is not None:
        entries = [entry for entry in entries if entry["duration"] > duration_gt]

    if duration_lt is not None:
        entries = [entry for entry in entries if entry["duration"] < duration_lt]

    return entries


def _job_sort_key(sort_by: SortBy):
    if sort_by == "name":
        return lambda entry: entry["name"]
    if sort_by == "status":
        return lambda entry: (_category(entry), _outcome(entry), entry["name"])
    if sort_by == "session":
        return lambda entry: (entry["session"], entry["name"])
    if sort_by == "duration":
        return lambda entry: entry["duration"]
    raise ValueError(f"invalid sort key {sort_by!r}")


def _session_name_from_dir(session_dir: Path) -> str:
    lockfile = session_dir / "session.lock"
    if lockfile.exists():
        data = json.loads(lockfile.read_text())
        return data.get("name", session_dir.name)
    return session_dir.name


def _measurements_from_row(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("measurements", {})

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}

    if isinstance(value, dict):
        return value

    return {}


def _duration(entry: dict[str, Any]) -> float:
    timings = entry.get("timings", {})
    running = timings.get("running", -1)
    total = timings.get("total", -1)

    if isinstance(running, (int, float)) and running >= 0:
        return float(running)

    if isinstance(total, (int, float)) and total >= 0:
        return float(total)

    return -1.0


def _category(entry: dict[str, Any]) -> str:
    return str(entry.get("status", {}).get("category", "")).upper()


def _outcome(entry: dict[str, Any]) -> str:
    return str(entry.get("status", {}).get("outcome", "")).upper()


def _is_passed(entry: dict[str, Any]) -> bool:
    return _category(entry) == "PASS" or _outcome(entry) == "PASSED"


def _is_failed(entry: dict[str, Any]) -> bool:
    return _outcome(entry) in _FAILED_OUTCOMES


def _is_timeout(entry: dict[str, Any]) -> bool:
    return _outcome(entry) in _TIMEOUT_OUTCOMES


def _is_diffed(entry: dict[str, Any]) -> bool:
    return _outcome(entry) in _DIFF_OUTCOMES


def _is_skipped(entry: dict[str, Any]) -> bool:
    return _category(entry) in _SKIP_CATEGORIES


def _is_cancelled(entry: dict[str, Any]) -> bool:
    return _category(entry) in _CANCEL_CATEGORIES


def _is_unfinished(entry: dict[str, Any]) -> bool:
    return _category(entry) in {"", "NONE"}


def _sql_string(statement: str | Sequence[str]) -> str:
    if isinstance(statement, str):
        return statement
    return " ".join(str(item) for item in statement)


def _normalize_json_path(path: str) -> str:
    """Normalize user-friendly JSON paths for Canary query helpers.

    The lower-level query helpers expect nested paths to be dotted, e.g.
    ``.measurements``.  The public API accepts both ``measurements`` and
    ``.measurements``.
    """

    if path in ("", "."):
        return "."

    if path.startswith(".") or path.startswith("["):
        return path

    return f".{path}"


def _raw_keys(data: Any, path: str) -> list[str]:
    selected = query_json(data, _normalize_json_path(path))

    if isinstance(selected, dict):
        return sorted(str(key) for key in selected.keys())

    if isinstance(selected, list):
        return [str(i) for i in range(len(selected))]

    return []


__all__ = [
    "cancelled_jobs",
    "cache",
    "db_schema",
    "db_stats",
    "diffed_jobs",
    "environment",
    "failures",
    "failed_jobs",
    "job",
    "job_history",
    "jobs",
    "latest_session",
    "measurement",
    "measurement_table",
    "measurements",
    "nonpassing_jobs",
    "passed_jobs",
    "raw_job_keys",
    "raw_job_lock",
    "raw_job_value",
    "raw_session_keys",
    "raw_session_lock",
    "raw_session_value",
    "running_jobs",
    "session",
    "session_summary",
    "sessions",
    "skipped_jobs",
    "sql",
    "timeout_jobs",
    "unfinished_jobs",
]
