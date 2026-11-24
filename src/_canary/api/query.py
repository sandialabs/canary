# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The /canary/query/* endpoints (read-only)."""

import sqlite3
from typing import Any

from _canary.app.queries import JobRecord
from _canary.app.queries import job_history
from _canary.app.queries import list_jobs
from _canary.app.queries import session_jobs
from _canary.core.status import Category

from .dispatch import Context
from .dispatch import EndpointRegistry
from .dispatch import RequestError
from .models import QueryDBRequest
from .models import QueryFailuresRequest
from .models import QueryJobRequest
from .models import QueryJobsRequest
from .models import QuerySessionRequest
from .models import QuerySessionsRequest
from .roots import public_path
from .roots import publish

#: Most rows /canary/query/db returns.
MAX_ROWS = 10_000

#: The categories /canary/query/failures reports.
FAILED = (Category.FAIL.value, Category.ABORTED.value)


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


def job(request: QueryJobRequest, ctx: Context) -> JobRecord:
    """The job's result in the session."""
    session = _session(request.session_id, ctx)
    views = job_history(resolve_job_id(request.job_id, ctx), start=ctx.workspace_root)
    found = [v for v in views if v["session"] == session]
    if not found:
        raise RequestError(404, f"no result for job {request.job_id!r} in session {session}")
    return publish(found[-1], ctx)


def session(request: QuerySessionRequest, ctx: Context) -> dict[str, Any]:
    """The session's outcome counts, and with ``expand_jobs`` every job's result."""
    name = _session(request.session_id, ctx)
    jobs = session_jobs(name, start=ctx.workspace_root)
    data: dict[str, Any] = {
        "session_id": name,
        "result_count": len(jobs),
        "outcome_counts": ctx.workspace.db.get_outcome_counts_for_session(name),
    }
    if request.expand_jobs:
        data["jobs"] = publish(jobs, ctx)
    return data


def sessions(request: QuerySessionsRequest, ctx: Context) -> list[str]:
    """Every session's name, oldest first (names sort by time)."""
    return sorted(p.name for p in ctx.workspace.sessions_dir.iterdir() if p.is_dir())


def jobs(request: QueryJobsRequest, ctx: Context) -> list[JobRecord]:
    """The latest result of every job; with ``session_id``, only those from that session."""
    views = list_jobs(start=ctx.workspace_root, details=True)
    if request.session_id is not None:
        name = _session(request.session_id, ctx)
        views = [v for v in views if v["session"] == name]
    return publish(views, ctx)


def failures(request: QueryFailuresRequest, ctx: Context) -> list[JobRecord]:
    """The session's jobs that failed or aborted."""
    name = _session(request.session_id, ctx)
    jobs = session_jobs(name, start=ctx.workspace_root)
    return publish([v for v in jobs if v["status"]["category"] in FAILED], ctx)


def db(request: QueryDBRequest, ctx: Context) -> dict[str, Any]:
    """The rows of one ``SELECT`` (at most ``MAX_ROWS``; ``truncated`` says if there were more).

    A column holding an absolute path (``file_root``, ``workspace``, ...) is published as a
    job record's paths are; paths inside JSON columns (``specs.data``) are returned as
    stored.
    """
    try:
        rows = ctx.workspace.db.select(request.sql, limit=MAX_ROWS + 1)
    except (ValueError, sqlite3.Error) as exc:
        raise RequestError(400, str(exc)) from None
    published = [
        {k: public_path(v, ctx) if isinstance(v, str) else v for k, v in row.items()}
        for row in rows[:MAX_ROWS]
    ]
    return {"rows": published, "truncated": len(rows) > MAX_ROWS}


def register(registry: EndpointRegistry) -> None:
    registry.register("/canary/query/job", job)
    registry.register("/canary/query/session", session)
    registry.register("/canary/query/sessions", sessions)
    registry.register("/canary/query/jobs", jobs)
    registry.register("/canary/query/failures", failures)
    registry.register("/canary/query/db", db)
