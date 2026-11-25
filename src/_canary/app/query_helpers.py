# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Workspace result helpers shared by ``canary query``, the app's query functions and plugins."""

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..workspace.session import Session
from ..workspace.workspace import Workspace
from .failure_analysis import collect_failure_groups
from .failure_analysis import failure_signature_for_row
from .failure_analysis import job_from_result_row
from .failure_analysis import list_existing_logs
from .failure_analysis import tail_lines
from .paths import remap_path

if TYPE_CHECKING:
    from ..core.job import Job


def resolve_session_dir(workspace: Workspace, session: str) -> Path:
    """Resolve a session name, prefix, or ``latest`` to its directory path."""
    if session == "latest":
        latest = workspace.refs_dir / "latest"
        if not latest.exists():
            raise FileNotFoundError(latest)
        rel = latest.read_text().strip()
        return (workspace.refs_dir / rel).resolve()

    candidate = workspace.sessions_dir / session
    if candidate.is_dir():
        return candidate

    matches = sorted(p for p in workspace.sessions_dir.glob(f"{session}*") if p.is_dir())
    if not matches:
        raise ValueError(f"{session!r}: no matching session found")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches[:8])
        if len(matches) > 8:
            names += ", ..."
        raise ValueError(f"{session!r}: ambiguous session prefix; matches: {names}")
    return matches[0]


def job_lockfile(workspace: Workspace, jobid: str, session: str | None = None) -> Path:
    """Resolve *jobid* to its ``testcase.lock`` path, raising if not found.

    With *session* (a name, prefix, or ``latest``), return the lock file written
    by that session's run of the job rather than the job's latest run.
    """
    job = workspace.find_job(jobid)
    if session is None:
        lockfile = job.lockfile
    else:
        session_dir = resolve_session_dir(workspace, session)
        row = job_row_in_session(workspace, job.id, session_dir.name)
        if row is None:
            raise ValueError(f"job {jobid!r} has no result in session {session_dir.name!r}")
        lockfile = session_dir / row["workspace"] / "testcase.lock"
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    return lockfile


def job_result_history(workspace: Workspace, job_id: str) -> list[dict[str, Any]]:
    """Return every result row for *job_id*, oldest session first."""
    workspace.db.connect()
    try:
        return list(workspace.db.get_result_history(job_id))
    finally:
        workspace.db.close()


def job_row_in_session(workspace: Workspace, job_id: str, session: str) -> dict[str, Any] | None:
    """Return the result row for *job_id* recorded by *session*, or ``None``."""
    for row in job_result_history(workspace, job_id):
        if row["session"] == session:
            return row
    return None


def find_cache_path(job: "Job") -> Path | None:
    """Return the path to the per-job timing cache file, or None if absent."""
    from ..history.store import HistoryStore

    store = HistoryStore.open(start=job.workspace.root)
    return store.path_for(job)


def db_results_for_session(workspace: Workspace, session_name: str) -> list[dict[str, Any]]:
    """Return all result rows for a given session from the workspace DB."""
    return workspace.db.get_results_for_session(session_name)


def db_outcome_counts_for_session(workspace: Workspace, session_name: str) -> dict[str, int]:
    """Return {outcome_name: count} for all jobs in a session."""
    from ..core.status import Outcome

    result: dict[str, int] = {}
    for raw_outcome, count in workspace.db.get_outcome_counts_for_session(session_name).items():
        try:
            name = Outcome.factory(raw_outcome).name
        except (ValueError, KeyError):
            name = str(raw_outcome)
        result[name] = count
    return result


def clean(data: Any) -> Any:
    """Recursively strip __type__ wrappers and normalise legacy enum dicts.

    Converts:
    - ``{"__type__": "...", "value": X}``  →  ``X``
    - Removes ``__type__`` keys from all other dicts
    """
    if isinstance(data, dict):
        # Legacy enum envelope: {"__type__": "...", "value": X}
        if "__type__" in data and set(data.keys()) <= {"__type__", "value"}:
            return clean(data["value"])
        # Strip __type__ from general dicts and recurse
        return {k: clean(v) for k, v in data.items() if k != "__type__"}
    elif isinstance(data, list):
        return [clean(item) for item in data]
    return data


_WHERE_RE = re.compile(
    r"^(?P<path>[A-Za-z_][A-Za-z0-9_.]*)\s*(?P<op>==|!=|>=|<=|>|<)\s*(?P<value>.+)$"
)


def parse_where(expr: str) -> Any:
    """Parse a --where expression and return a predicate callable.

    Supported syntax:  ``key.path OP value``
    where OP is one of  ==  !=  >  <  >=  <=
    and value is treated as a string (case-insensitive for status fields).
    Numeric fields (int/float) are compared numerically so that expressions
    like ``timings.queue_wait>3600`` work correctly.  If the actual field
    value is ``None`` (e.g. a batch whose timing has not yet been recorded),
    ordered comparisons (``>  <  >=  <=``) return ``False``; equality (``==``)
    also returns ``False`` while ``!=`` returns ``True``.
    """
    m = _WHERE_RE.match(expr.strip())
    if not m:
        raise ValueError(
            f"Invalid --where expression {expr!r}. "
            "Expected format: key.path==value  (e.g. status.outcome==FAILED)"
        )
    path = m.group("path")
    op = m.group("op")
    raw_value = m.group("value").strip()

    def _get(obj: Any, dotpath: str) -> Any:
        for part in dotpath.split("."):
            if not isinstance(obj, dict):
                return None
            obj = obj.get(part)
        return obj

    def _coerce(actual: Any, expected: str) -> tuple[Any, Any] | None:
        """Try to coerce expected to the same type as actual for comparison.

        Returns None when actual is None (caller should handle the null case).
        """
        if actual is None:
            return None
        if isinstance(actual, (int, float)):
            try:
                return actual, type(actual)(expected)
            except (ValueError, TypeError):
                pass
        # Fall back to string comparison (case-insensitive for outcomes/categories)
        return str(actual).upper(), expected.upper()

    def predicate(obj: dict[str, Any]) -> bool:
        actual = _get(obj, path)
        coerced = _coerce(actual, raw_value)
        if coerced is None:
            # actual is None — ordered comparisons are False; != is True
            return op == "!="
        a, b = coerced
        if op == "==":
            return a == b
        elif op == "!=":
            return a != b
        elif op == ">":
            return a > b  # type: ignore[operator]
        elif op == "<":
            return a < b  # type: ignore[operator]
        elif op == ">=":
            return a >= b  # type: ignore[operator]
        elif op == "<=":
            return a <= b  # type: ignore[operator]
        return False

    return predicate


def job_blockers(
    workspace: Workspace, jobid: str, *, recursive: bool = False, signatures: bool = False
) -> dict[str, Any]:
    job = workspace.find_job(jobid)
    seed_ids = {job.id}
    dep_ids = (
        workspace.db.get_upstream_ids(seed_ids)
        if recursive
        else set(dep.job.id for dep in job.dependencies)
    )
    if not dep_ids:
        return {
            "id": job.id,
            "name": job.name,
            "outcome": job.status.outcome.name,
            "blocked_by": {"total_deps": 0, "failed": 0, "passed": 0, "root_signatures": []},
        }

    dep_rows = workspace.db.get_results(list(dep_ids))
    failed_rows = [row for row in dep_rows.values() if row["status"].category.value == "FAIL"]
    passed_rows = [row for row in dep_rows.values() if row["status"].category.value == "PASS"]
    root_signatures: list[dict[str, Any]] = []
    if signatures:
        grouped = collect_failure_groups(workspace, failed_rows)
        root_signatures = [
            {"signature": group["signature_normalized"], "count": group["count"]}
            for group in grouped
        ]

    return {
        "id": job.id,
        "name": job.name,
        "outcome": job.status.outcome.name,
        "blocked_by": {
            "total_deps": len(dep_ids),
            "failed": len(failed_rows),
            "passed": len(passed_rows),
            "root_signatures": root_signatures,
        },
    }


def batch_timings_for_job(
    workspace: Workspace, job_id: str, session: str, cache: dict | None = None
) -> dict[str, float]:
    """Look up batch-level timings for a job whose own timekeeper is empty.

    Scans ``sessions/<session>/hpc.batches/*/batch.lock`` files for one whose
    ``jobs`` list contains *job_id*.  Returns a timings dict with keys
    ``pending``, ``setup``, ``running``, ``teardown``, ``total`` where
    available, defaulting to ``-1.0``.  Also includes ``_started_at`` and
    ``_stopped_at`` as absolute unix epoch floats (``-1.0`` when unavailable)
    so callers can use them for overlap/concurrency analysis without a second
    batch-lock scan.  All duration values are rounded to 6 decimal places.

    This is a best-effort fallback for HPC one-job-per-batch Slurm runs where
    the child job's timekeeper only gets coarse timestamps (the batch wall-clock
    start/stop), not the fine-grained phase breakdown recorded by local workers.
    Returns an all-``-1.0`` dict when no matching batch is found.
    """
    import json as _json

    empty: dict[str, float] = {
        "pending": -1.0,
        "setup": -1.0,
        "running": -1.0,
        "teardown": -1.0,
        "total": -1.0,
        "_started_at": -1.0,
        "_stopped_at": -1.0,
    }
    data = _batch_lock_for_job(workspace, job_id, session, cache)
    if data is not None:
        # Found the owning batch — derive timings from its timekeeper.
        tk = data.get("timekeeper", {})
        if isinstance(tk, str):
            try:
                tk = _json.loads(tk)
            except ValueError:
                tk = {}
        b_submitted: float = float(tk.get("_submitted", -1) or -1)
        b_started: float = float(tk.get("_started", -1) or -1)
        b_stopped: float = float(tk.get("_stopped", -1) or -1)

        def _el(a: float, b: float) -> float:
            return round(b - a, 6) if a > 0 and b > 0 else -1.0

        return {
            # pending = queue wait (batch submitted → Slurm job started)
            "pending": _el(b_submitted, b_started),
            # setup = 0 for HPC (no staging separate from start)
            "setup": -1.0,
            # running = actual compute time (Slurm start → stop)
            "running": _el(b_started, b_stopped),
            # teardown not tracked separately at batch level
            "teardown": -1.0,
            # total = wall time from submission to completion
            "total": _el(b_submitted, b_stopped),
            # absolute epoch timestamps for overlap/concurrency analysis
            "_started_at": b_started if b_started > 0 else -1.0,
            "_stopped_at": b_stopped if b_stopped > 0 else -1.0,
        }
    return empty


def batch_last_activity_for_job(
    workspace: Workspace, job_id: str, session: str, cache: dict | None = None
) -> float | None:
    """Return the ``last_activity`` unix timestamp from the owning batch.lock.

    Scans ``sessions/<session>/hpc.batches/*/batch.lock`` files for one whose
    ``jobs`` list contains *job_id* and returns the ``last_activity`` field if
    present.  Returns ``None`` when no match is found or the field is absent
    (e.g. the batch has not started or was written by an older canary version).
    """
    data = _batch_lock_for_job(workspace, job_id, session, cache)
    if data is None:
        return None
    val = data.get("last_activity")
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass
    return None


def _batch_lock_for_job(
    workspace: Workspace, job_id: str, session: str, cache: dict | None = None
) -> dict[str, Any] | None:
    """The first ``hpc.batches/*/batch.lock`` (in glob order) whose ``jobs`` list has *job_id*.

    With *cache* (a dict the caller keeps for one listing), each session's batch locks are
    read once and indexed by job id, instead of once per job.
    """

    if cache is not None:
        key = ("batches", session)
        if key not in cache:
            cache[key] = index = {}
            for data in _batch_locks(workspace, session):
                for jid in data.get("jobs", []):
                    index.setdefault(jid, data)
        return cache[key].get(job_id)
    for data in _batch_locks(workspace, session):
        if job_id in data.get("jobs", []):
            return data
    return None


def _batch_locks(workspace: Workspace, session: str) -> Any:
    import json as _json

    batches_dir = workspace.sessions_dir / session / "hpc.batches"
    if not batches_dir.is_dir():
        return
    for batch_lock in batches_dir.glob("*/batch.lock"):
        try:
            yield _json.loads(batch_lock.read_text())
        except (OSError, ValueError):  # nosec B112 — skip unreadable/malformed lock files
            continue


def entry_duration(timings: dict[str, float]) -> float | None:
    """Return the job's recorded duration: running time, else total, else ``None``.

    Matches ``testcase.lock``'s ``timekeeper.duration`` (the running phase) for
    local jobs, and falls back to the batch wall-clock for HPC child jobs.
    """
    for key in ("running", "total"):
        value = timings.get(key, -1.0)
        if value is not None and value >= 0:
            return value
    return None


#: The timings of a job that has not run.
NO_TIMINGS = {"pending": -1.0, "setup": -1.0, "running": -1.0, "teardown": -1.0, "total": -1.0}


def spec_to_job_entry(workspace: Workspace, spec: Any) -> dict[str, Any]:
    """The job entry of a spec that has no result yet (collected, never run)."""
    return {
        "id": spec.id,
        "name": spec.name,
        "fullname": spec.fullname,
        "file_root": str(spec.file_root),
        "file_path": str(spec.file_path),
        "exec_path": str(spec.exec_path),
        "exec_dir": None,
        "session": "",
        "phase": "",
        "exit_code": None,
        "status": {"category": "NOTRUN", "outcome": "NONE", "reason": "not run yet"},
        "timings": dict(NO_TIMINGS),
        "duration": None,
        "started_at": None,
        "stopped_at": None,
        "last_activity": None,
        "measurements": {},
    }


def row_to_job_entry(
    workspace: Workspace, row: dict[str, Any], cache: dict | None = None, *, details: bool = True
) -> dict[str, Any]:
    """Convert a DB result row dict into the standard job entry: the one job record.

    Every interface shows a job this way: ``canary query``, the API's endpoints,
    ``app.status`` (which adds its booleans) and the TUI (which derives its display fields).
    Its paths are canary's own: ``file_root`` is the generator's absolute root and
    ``file_path`` the generator's path relative to it -- the same relative path that lays
    out the session directory and the view; ``exec_path`` is the job's directory relative
    to the session directory and ``exec_dir`` that directory, absolute.  (The API publishes
    ``file_root`` and ``exec_dir`` its own way: :mod:`_canary.api.roots`.)

    Used by both ``_exec_session_expand`` and ``_exec_jobs`` to ensure a
    consistent record shape.

    Timings are derived from the job's own ``timekeeper`` when available.  For
    HPC one-job-per-batch Slurm runs the child job's per-phase timestamps are
    often ``-1.0`` (the fine-grained lifecycle is tracked at the batch level).
    In that case the function falls back to scanning the owning
    ``batch.lock`` and mapping the batch-level wall-clock phases to the
    standard timing keys (``pending`` = queue wait, ``running`` = compute
    wall-clock, ``total`` = submission-to-completion).

    ``started_at`` and ``stopped_at`` are absolute unix epoch floats marking
    when the job's actual execution began and ended.  For local-worker jobs
    these come from ``timekeeper._started`` / ``timekeeper._stopped``.  For
    HPC batch jobs they fall back to the batch-level Slurm start/stop times.
    Both are ``null`` when no timestamp is available.  These fields enable
    overlap/concurrency analysis without reading raw lock files.

    With *details* false the record comes from the SQL row alone, reading no file: the
    HPC batch-lock fallback is skipped (``timings``, ``started_at`` and ``stopped_at``
    are the job's own; ``last_activity`` is ``None``).  Listings that must stay fast
    (``canary status``-like views, the TUI) use that.  *cache* (a dict kept for one
    listing) saves re-reading a session's batch locks for every job.

    The ``last_activity`` field is a unix epoch float recording the most recent
    time the owning batch's output file was written to.  It is populated from
    the ``last_activity`` key in the owning ``batch.lock`` (written by the
    ``batchexec`` polling loop) and is ``null`` for local-worker jobs or when
    the batch has not yet started writing output.  Callers should treat it as
    an I/O liveness signal, NOT as a measure of application progress.
    """
    tk = row["timekeeper"]

    def _tk_get(key: str) -> float:
        """Extract a timekeeper field whether tk is a dict or a Timekeeper object."""
        if isinstance(tk, dict):
            return float(tk.get(key, -1) or -1)
        return float(getattr(tk, key, -1) or -1)

    submitted = _tk_get("_submitted")
    staged = _tk_get("_staged")
    started = _tk_get("_started")
    stopped = _tk_get("_stopped")
    finished = _tk_get("_finished")

    def elapsed(a: float, b: float) -> float:
        return round(b - a, 6) if a > 0 and b > 0 else -1.0

    timings = {
        "pending": elapsed(submitted, staged),
        "setup": elapsed(staged, started),
        "running": elapsed(started, stopped),
        "teardown": elapsed(stopped, finished),
        "total": elapsed(submitted, finished),
    }

    # started_at / stopped_at from the job's own timekeeper (local workers).
    started_at: float | None = float(started) if started > 0 else None
    stopped_at: float | None = float(stopped) if stopped > 0 else None

    # Fall back to batch-level timings for HPC child jobs whose own timekeeper
    # has no meaningful phase data (all -1.0).  This is the common case for
    # one-job-per-batch Slurm runs where fine-grained lifecycle events are
    # tracked at the batch level, not the individual job level.
    if details and all(v < 0 for v in timings.values()):
        batch_timings = batch_timings_for_job(workspace, row["id"], row["session"], cache)
        timings = {k: v for k, v in batch_timings.items() if not k.startswith("_")}
        if started_at is None:
            b_started = batch_timings.get("_started_at", -1.0)
            started_at = float(b_started) if b_started > 0 else None
        if stopped_at is None:
            b_stopped = batch_timings.get("_stopped_at", -1.0)
            stopped_at = float(b_stopped) if b_stopped > 0 else None

    # last_activity: HPC batch I/O liveness signal from the owning batch.lock.
    # None for local-worker jobs (no batch) or when the batch has not started.
    last_activity = (
        batch_last_activity_for_job(workspace, row["id"], row["session"], cache)
        if details
        else None
    )

    session_dir = workspace.sessions_dir / row["session"]
    anchor = workspace.root.parent
    if Path(row["workspace"]).is_absolute():
        # Recorded absolute: remap it from the root the session was created under.
        try:
            root_at_creation = Session.load_lock_data(session_dir).get("root_at_creation")
        except FileNotFoundError:
            root_at_creation = None
        exec_dir = remap_path(
            row["workspace"], root_at_creation=root_at_creation, current_root=anchor
        )
    else:  # the usual case: relative to the session directory, under the current root
        exec_dir = str(session_dir / row["workspace"])
    return {
        "id": row["id"],
        "name": row["spec_name"],
        "fullname": row["spec_fullname"],
        "file_root": row.get("file_root") or "",
        "file_path": row.get("file_path", ""),
        "exec_path": row["workspace"],
        "exec_dir": exec_dir,
        "session": row["session"],
        "phase": getattr(getattr(row["state"], "phase", None), "name", "") or "",
        "exit_code": row["status"].code,
        "status": {
            "category": row["status"].category.value,
            "outcome": row["status"].outcome.name,
            "reason": row["status"].reason,
        },
        "timings": timings,
        "duration": entry_duration(timings),
        "started_at": started_at,
        "stopped_at": stopped_at,
        "last_activity": last_activity,
        "measurements": _measurements(row.get("measurements")),
    }


def _measurements(measurements: Any) -> dict[str, Any]:
    """A result row's measurements as plain data (``{}`` if it has none)."""
    data = getattr(measurements, "data", measurements)
    return dict(data) if isinstance(data, dict) else {}


def session_summary(workspace: Workspace, session_dir: Path) -> dict[str, Any] | None:
    """One line of ``canary query sessions``: *session_dir*'s run and outcome counts.

    ``None`` if *session_dir* is not a session (no ``session.lock``).
    """
    if not session_dir.is_dir():
        return None
    lockfile = session_dir / "session.lock"
    if not lockfile.exists():
        return None
    session_data = json.loads(lockfile.read_text())
    session_name = session_data.get("name", session_dir.name)

    counts = db_outcome_counts_for_session(workspace, session_name)
    total = sum(counts.values())

    return {
        "name": session_name,
        "started_on": session_data.get("started_on"),
        "finished_on": session_data.get("finished_on"),
        "returncode": session_data.get("returncode"),
        "error": session_data.get("error"),
        "argv": session_data.get("argv", []),
        "job_count": total,
        "outcomes": counts,
    }


def rows_for_named_session(workspace: Workspace, session_name: str) -> list[dict[str, Any]]:
    session_dir = resolve_session_dir(workspace, session_name)
    return db_results_for_session(workspace, session_dir.name)


def build_compare_row(
    workspace: Workspace,
    base_row: dict[str, Any] | None,
    new_row: dict[str, Any] | None,
    *,
    include_signatures: bool,
) -> dict[str, Any]:
    if base_row is None and new_row is None:
        raise ValueError("compare row requires at least one side")
    if base_row is None:
        assert new_row is not None
        new_entry = row_to_job_entry(workspace, new_row)
        return {
            "kind": "new_jobs",
            "id": new_row["id"],
            "name": new_row["spec_name"],
            "base": None,
            "new": new_row["status"].outcome.name,
            "new_status": new_entry["status"],
        }
    if new_row is None:
        assert base_row is not None
        base_entry = row_to_job_entry(workspace, base_row)
        return {
            "kind": "missing_in_new",
            "id": base_row["id"],
            "name": base_row["spec_name"],
            "base": base_row["status"].outcome.name,
            "new": None,
            "base_status": base_entry["status"],
        }

    assert base_row is not None
    assert new_row is not None
    base_entry = row_to_job_entry(workspace, base_row)
    new_entry = row_to_job_entry(workspace, new_row)
    base_nonpass = base_entry["status"]["category"] != "PASS"
    new_nonpass = new_entry["status"]["category"] != "PASS"
    compare_row: dict[str, Any] = {
        "id": new_row["id"],
        "name": new_row["spec_name"],
        "base": base_row["status"].outcome.name,
        "new": new_row["status"].outcome.name,
        "base_status": base_entry["status"],
        "new_status": new_entry["status"],
    }

    if base_nonpass and not new_nonpass:
        compare_row["kind"] = "fixed"
        return compare_row
    if not base_nonpass and new_nonpass:
        compare_row["kind"] = "new_failures"
        if include_signatures:
            signature = failure_signature_for_row(workspace, new_row)
            compare_row["signature"] = (
                None if signature is None else signature["signature_normalized"]
            )
        return compare_row
    if base_nonpass and new_nonpass:
        compare_row["kind"] = "still_failing"
        compare_row["signature_changed"] = False
        if include_signatures:
            base_signature = failure_signature_for_row(workspace, base_row)
            new_signature = failure_signature_for_row(workspace, new_row)
            compare_row["base_signature"] = (
                None if base_signature is None else base_signature["signature_normalized"]
            )
            compare_row["new_signature"] = (
                None if new_signature is None else new_signature["signature_normalized"]
            )
            compare_row["signature_changed"] = (
                compare_row["base_signature"] != compare_row["new_signature"]
            )
        return compare_row

    compare_row["kind"] = "unchanged_pass"
    return compare_row


def compare_digest(compare_row: dict[str, Any]) -> str:
    base = compare_row.get("base") or "MISSING"
    new = compare_row.get("new") or "MISSING"
    suffix = " [sig changed]" if compare_row.get("signature_changed") else ""
    return f"{compare_row['name']} {base}->{new}{suffix}"


def apply_with_fields(
    workspace: Workspace, row: dict[str, Any], entry: dict[str, Any], with_fields: list[str] | None
) -> None:
    if not with_fields:
        return
    requested = [field for field in with_fields if field and field.startswith("logs")]
    if not requested:
        return
    job = job_from_result_row(workspace, row)
    logs = list_existing_logs(job)
    tail_n = None
    for field in requested:
        _, _, suffix = field.partition(":")
        if suffix:
            tail_n = int(suffix)
            break
    if tail_n is not None:
        for item in logs:
            item["tail"] = tail_lines(Path(item["path"]), tail_n)
    entry["logs"] = logs
