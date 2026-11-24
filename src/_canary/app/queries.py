# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application read-model queries for interfaces (TUI/GUI/CLI/API).

These functions project the workspace's persisted results into the one job record
(:data:`JobRecord`) so that an interface never has to touch the database, reconstruct
domain objects, or know Canary's internal types; an interface derives its own display
fields from it (the TUI's :class:`~_canary.tui.views.JobView`).  This keeps the business logic in the application layer and the
interfaces as thin adapters (see the redesign's interface architecture: CLI,
TUI, GUI, and REST all sit on the same ``canary.app`` surface).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import TypedDict

from ..workspace.workspace import Workspace
from .query_helpers import row_to_job_entry
from .query_helpers import spec_to_job_entry

__all__ = [
    "JobRecord",
    "WorkspaceSummary",
    "job_history",
    "job_log",
    "list_jobs",
    "session_jobs",
    "workspace_summary",
]


JobRecord = dict[str, Any]
"""The one job record every interface shows (see :func:`.query_helpers.row_to_job_entry`).

``id``, ``name``, ``fullname``, ``file_path`` and ``exec_dir`` (relative to the workspace's
anchor when under it), ``session``, ``phase``, ``exit_code``, ``status`` (``category``,
``outcome``, ``reason``), ``timings``, ``duration``, ``started_at``, ``stopped_at`` and
``last_activity``.  A collected spec with no result yet has category ``NOTRUN``, an empty
``session`` and no timings.
"""


def job_history(spec_id: str, start: Path | str | None = None) -> list[JobRecord]:
    """Every result recorded for *spec_id*, oldest first.

    Args:
        spec_id: The spec ID (or a prefix) to get history for
        start: Optional workspace root or start path for workspace search
    """
    ws = Workspace.load(start) if start else Workspace.load()
    cache: dict = {}
    return [row_to_job_entry(ws, r, cache) for r in ws.db.get_result_history(spec_id)]


def session_jobs(session: str, start: Path | str | None = None) -> list[JobRecord]:
    """Every result recorded in *session*, ordered by name.

    Args:
        session: The session's name
        start: Optional workspace root or start path for workspace search
    """
    ws = Workspace.load(start) if start else Workspace.load()
    cache: dict = {}
    return [row_to_job_entry(ws, r, cache) for r in ws.db.get_results_for_session(session)]


def list_jobs(
    ids: list[str] | None = None,
    include_upstreams: bool = False,
    start: Path | str | None = None,
    *,
    details: bool = False,
) -> list[JobRecord]:
    """The latest result of every collected spec (or of *ids*), ordered by name.

    Specs that were collected but never ran are included (category ``NOTRUN``) so
    interfaces can select and launch them.

    Args:
        ids: Optional list of spec IDs to filter to
        include_upstreams: Whether to include upstream dependencies
        start: Optional workspace root or start path for workspace search
        details: Read each HPC session's batch locks for batch timings and
            ``last_activity`` (``canary query``'s detail).  Off by default: the
            listing then comes from the database alone, fast enough for status views.
    """
    ws = Workspace.load(start) if start else Workspace.load()
    db = ws.db
    specs = db.load_specs(ids, include_upstreams=include_upstreams)
    results = db.get_results(ids, include_upstreams=include_upstreams)
    cache: dict = {}
    records: list[JobRecord] = []
    for spec in specs:
        result = results.get(spec.id)
        if result is not None:
            records.append(row_to_job_entry(ws, result, cache, details=details))
        else:
            records.append(spec_to_job_entry(ws, spec))
    records.sort(key=lambda r: (r["name"], r["id"]))
    return records


def job_log(spec_id: str, *, stream: str = "stdout") -> str:
    """Return the captured output of a job's execution as text.

    Resolves the job for *spec_id* in the current workspace and reads the file
    for the requested *stream* (``"stdout"`` or ``"stderr"``) from the job's
    execution directory.  Returns an empty string when the job has not produced
    that stream (e.g. it never ran, or wrote no stderr), so callers -- an
    interface showing a not-yet-run job -- do not have to special-case a missing
    file.

    Raises:
        ValueError: If *spec_id* matches no job in the workspace.
    """
    job = Workspace.load().find(job=spec_id)
    if stream == "stderr":
        relpath = job.stderr
    else:
        relpath = job.stdout
    if relpath is None:
        return ""
    path = job.workspace.joinpath(relpath)
    if not path.exists():
        return ""
    return path.read_text()


class WorkspaceSummary(TypedDict):
    """A render-ready summary of the current workspace."""

    root: str
    session_count: int
    latest_session: str
    spec_count: int
    tags: list[str]
    version: str


def workspace_summary() -> WorkspaceSummary:
    """Return a render-ready :class:`WorkspaceSummary` for the current workspace."""
    info = Workspace.load().info()
    return WorkspaceSummary(
        root=str(info.get("root", "")),
        session_count=int(info.get("session_count", 0)),
        latest_session=str(info.get("latest_session") or ""),
        spec_count=len(info.get("specs", []) or []),
        tags=list(info.get("tags", []) or []),
        version=str(info.get("version", "")),
    )
