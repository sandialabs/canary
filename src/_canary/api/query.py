# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/query/* endpoints (read-only)."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from _canary.app.paths import locate
from _canary.app.queries import JobRecord
from _canary.app.queries import job_document
from _canary.app.queries import list_jobs
from _canary.app.queries import lookup
from _canary.app.queries import session_document
from _canary.app.queries import session_jobs
from _canary.app.queries import session_summaries
from _canary.app.query_helpers import clean
from _canary.core.job import unnest_measurements
from _canary.core.status import Category

from .dispatch import Context
from .dispatch import EndpointRegistry
from .dispatch import RequestError
from .models import LocationRequest
from .models import QueryDBRequest
from .models import QueryDBSchemaRequest
from .models import QueryDBStatsRequest
from .models import QueryFailuresRequest
from .models import QueryJobLogRequest
from .models import QueryJobRequest
from .models import QueryJobsRequest
from .models import QuerySessionRequest
from .models import QuerySessionsRequest
from .roots import public_path
from .roots import publish

#: Most rows /canary/query/db returns.
MAX_ROWS = 10_000

#: The categories /canary/query/failures reports, and the pass it reports too.
FAILED = (Category.FAIL.value, Category.ABORTED.value)
PASS_WITH_ERRORS = "PASS_WITH_ERRORS"


def needs_attention(record: JobRecord) -> bool:
    """A job that failed or aborted, or passed but a hook after it failed."""
    status = record["status"]
    return status["category"] in FAILED or status["outcome"] == PASS_WITH_ERRORS


def _session(session_id: str, ctx: Context) -> str:
    """*session_id*, with ``latest`` resolved; 404 if there is no such session."""
    if session_id == "latest":
        latest = ctx.workspace.latest_session()
        if not latest:
            raise RequestError(404, "the workspace has no sessions")
        return latest
    if not (ctx.workspace.sessions_dir / session_id).is_dir():
        raise RequestError(404, f"no session {session_id!r}")
    return session_id


def resolve_job_id(job_id: str, ctx: Context) -> str:
    """The full spec ID of *job_id* (an ID prefix or a name); 400 if ambiguous, 404 if unknown."""
    try:
        spec_id = ctx.workspace.db.resolve_spec_id(job_id)
    except ValueError as exc:
        raise RequestError(400, str(exc)) from None
    if spec_id is not None:
        return spec_id
    try:
        return ctx.workspace.find_jobspec(job_id).id
    except ValueError as exc:
        raise RequestError(404, str(exc)) from None


def _part(document: Any, path: str) -> Any:
    """The part of *document* at *path*; 404 naming what is there if nothing is."""
    try:
        return lookup(document, path)
    except LookupError as exc:
        raise RequestError(404, str(exc).strip("'\"")) from None


def job(request: QueryJobRequest, ctx: Context) -> Any:
    """One run of a job: its record, measurements, spec, resources and environment.

    The job's latest run, or its run in ``session_id``.  Further route segments select
    part of it (``/canary/query/job/ID/measurements/loss``, ``.../spec/parameters``); ``env``
    is the run's environment, there only when asked for.
    """
    session = _session(request.session_id, ctx) if request.session_id is not None else None
    keys = [k for k in request.path.split("/") if k]
    try:
        document = job_document(
            resolve_job_id(request.job_id, ctx),
            session,
            start=ctx.workspace_root,
            env=bool(keys) and keys[0] == "env",
        )
    except LookupError as exc:
        raise RequestError(404, str(exc)) from None
    return _part(publish(document, ctx), request.path)


def job_log(request: QueryJobLogRequest, ctx: Context) -> dict[str, Any]:
    """What a run of a job printed (its ``canary-out.txt``), whole or its last ``tail`` lines.

    ``{"path": ..., "text": ..., "lines": N}``: the file (relative to the workspace), its
    text, and how many lines the file has.  The job's latest run, or its run in
    ``session_id``.  A job that wrote nothing to the stream: ``404``.
    """
    session = _session(request.session_id, ctx) if request.session_id is not None else None
    try:
        document = job_document(
            resolve_job_id(request.job_id, ctx), session, start=ctx.workspace_root
        )
    except LookupError as exc:
        raise RequestError(404, str(exc)) from None
    file = _output_file(document["exec_dir"], request.stream)
    if file is None:
        what = (
            "no stderr of its own (it goes to stdout)"
            if request.stream == "stderr"
            else "no output"
        )
        raise RequestError(404, f"job {request.job_id!r} has {what}")
    lines = file.read_text(errors="replace").splitlines(keepends=True)
    shown = lines[-request.tail :] if request.tail else lines
    return {"path": public_path(str(file), ctx), "text": "".join(shown), "lines": len(lines)}


def session(request: QuerySessionRequest, ctx: Context) -> Any:
    """A session: its outcome counts, how it ran (``session.lock``) and every job's record.

    Further route segments select part of it (``/canary/query/session/latest/outcome_counts``,
    ``.../jobs/0/measurements``).
    """
    document = session_document(_session(request.session_id, ctx), start=ctx.workspace_root)
    document["jobs"] = publish(document["jobs"], ctx)
    return _part(document, request.path)


def sessions(request: QuerySessionsRequest, ctx: Context) -> list[dict[str, Any]]:
    """Every session's summary (as `canary query sessions`), oldest first."""
    return session_summaries(start=ctx.workspace_root)


def jobs(request: QueryJobsRequest, ctx: Context) -> list[JobRecord]:
    """The latest result of every job; with ``session_id``, only those from that session."""
    views = list_jobs(start=ctx.workspace_root, details=True)
    if request.session_id is not None:
        name = _session(request.session_id, ctx)
        views = [v for v in views if v["session"] == name]
    return publish(views, ctx)


def _output_file(exec_dir: str, stream: str = "stdout") -> Path | None:
    """The file a run (in *exec_dir*) wrote *stream* to, if it did (its lock names it)."""
    lockfile = Path(exec_dir) / "testcase.lock"
    try:
        name = (json.loads(lockfile.read_text()).get("spec") or {}).get(stream)
    except (OSError, ValueError):
        return None
    file = Path(exec_dir) / name if name else None
    return file if file is not None and file.is_file() else None


def _tail(file: Path, lines: int) -> str:
    return "".join(file.read_text(errors="replace").splitlines(keepends=True)[-lines:])


def failures(request: QueryFailuresRequest, ctx: Context) -> list[JobRecord]:
    """The session's jobs that failed or aborted, or passed with errors (a hook failed).

    With ``log_tail``, each also has ``log_tail``: the last lines of what it printed (as
    ``/canary/query/job/ID/log`` with ``tail``), or ``null`` if it printed nothing.
    """
    name = _session(request.session_id, ctx)
    jobs = [v for v in session_jobs(name, start=ctx.workspace_root) if needs_attention(v)]
    if request.log_tail:
        for job in jobs:
            file = _output_file(job["exec_dir"])
            job["log_tail"] = _tail(file, request.log_tail) if file is not None else None
    return publish(jobs, ctx)


def db(request: QueryDBRequest, ctx: Context) -> dict[str, Any]:
    """The rows of one ``SELECT`` (at most ``MAX_ROWS``; ``truncated`` says if there were more).

    ``/canary/query/db/schema`` has the tables and their columns.  ``?`` in ``sql`` takes the
    next of ``params``.  A column holding an absolute path (``file_root``, ``workspace``,
    ...) is published as a job record's paths are; paths inside JSON columns
    (``specs.data``) are returned as stored.  With ``parse_json``, JSON columns come as
    objects (a ``measurements`` column as name to value, as in job records).
    """
    try:
        rows = ctx.workspace.db.select(request.sql, tuple(request.params), limit=MAX_ROWS + 1)
    except ValueError as exc:
        raise RequestError(400, str(exc)) from None
    except sqlite3.Error as exc:
        raise RequestError(400, f"{exc} (GET /canary/query/db/schema lists the columns)") from None
    published = [
        {k: _column(k, v, request.parse_json, ctx) for k, v in row.items()}
        for row in rows[:MAX_ROWS]
    ]
    return {"rows": published, "truncated": len(rows) > MAX_ROWS}


def _column(name: str, value: Any, parse_json: bool, ctx: Context) -> Any:
    """A result column's *value* as the API shows it."""
    if not isinstance(value, str):
        return value
    if parse_json and value[:1] in ("{", "["):
        try:
            parsed = clean(json.loads(value))
        except ValueError:
            return value
        if name == "measurements" and isinstance(parsed, dict):
            return unnest_measurements(parsed)
        return parsed
    return public_path(value, ctx)


def db_schema(request: QueryDBSchemaRequest, ctx: Context) -> Any:
    """The database's tables: each one's ``columns`` (name, type, notnull, pk) and ``sql``.

    Further route segments select part of it (``.../schema/results/columns``).
    """
    database = ctx.workspace.db
    ddl = database.get_schema()
    tables = {t: {"columns": cols, "sql": ddl.get(t)} for t, cols in database.get_columns().items()}
    return _part(tables, request.path)


def db_stats(request: QueryDBStatsRequest, ctx: Context) -> dict[str, Any]:
    """Counts of specs, results and sessions, the latest session, and the latest outcomes."""
    return ctx.workspace.db.get_stats()


def location(request: LocationRequest, ctx: Context) -> dict[str, Any]:
    """Where a job's files are, as `canary location`: its directory, log, input file and source.

    ``exec_dir`` (``-x``: its entry in the view, else its session directory), ``log``
    (``-l``), ``input`` (``-i``: the file that defines it) and ``source_dir`` (``-s``).
    Paths are relative to the workspace (or ``name:path`` under an allowed root), so they
    open from any machine that mounts it.
    """
    job_id = resolve_job_id(request.job_id, ctx)
    kinds = {
        "exec_dir": {},
        "log": {"show_log": True},
        "input": {"show_input": True},
        "source_dir": {"show_source_dir": True},
    }
    found: dict[str, Any] = {"id": job_id}
    for key, kind in kinds.items():
        try:
            (item,) = locate([job_id], start=ctx.workspace_root, **kind)
        except ValueError:  # e.g. a collected job that never ran has no directory
            found[key] = None
            continue
        found[key] = public_path(str(item["path"]), ctx)
    return found


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/query/job/{job_id}", job)
    registry.register("/canary/query/job/{job_id}/log", job_log)
    registry.register("/canary/query/job/{job_id}/{path:path}", job)
    registry.register("/canary/query/session/{session_id}", session)
    registry.register("/canary/query/session/{session_id}/{path:path}", session)
    registry.register("/canary/query/sessions", sessions)
    registry.register("/canary/query/jobs", jobs)
    registry.register("/canary/query/failures", failures)
    registry.register("/canary/location/{job_id}", location)
    registry.register("/canary/query/db", db)
    registry.register("/canary/query/db/schema", db_schema)
    registry.register("/canary/query/db/schema/{path:path}", db_schema)
    registry.register("/canary/query/db/stats", db_stats)
