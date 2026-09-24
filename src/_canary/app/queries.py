# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application read-model queries for interfaces (TUI/GUI/CLI).

These functions project the workspace's persisted result records into plain,
render-ready dictionaries (:data:`JobView`) so that an interface never has to
touch the database, reconstruct domain objects, or know Canary's internal
types.  This keeps the business logic in the application layer and the
interfaces as thin adapters (see the redesign's interface architecture: CLI,
TUI, GUI, and REST all sit on the same ``canary.app`` surface).
"""

from __future__ import annotations

from typing import Any
from typing import TypedDict

from .facade import get_event_bus
from .facade import get_job_log
from .facade import get_result_history
from .facade import get_results
from .facade import get_workspace_info

__all__ = [
    "JobView",
    "WorkspaceSummary",
    "get_event_bus",
    "job_history",
    "job_log",
    "list_jobs",
    "status_counts",
    "workspace_summary",
]


class JobView(TypedDict):
    """A flat, render-ready projection of a job's latest result.

    Every value is a primitive (``str``/``float``/``int``) so interfaces can
    display it directly without importing any ``_canary`` type.
    """

    id: str
    short_id: str
    name: str
    fullname: str
    file_path: str
    phase: str
    status: str
    status_label: str
    status_markup: str
    status_glyph: str
    category: str
    outcome: str
    reason: str
    duration: float
    session: str


def _job_view(result: dict[str, Any]) -> JobView:
    """Convert one ``get_results`` record into a :class:`JobView`."""
    status = result["status"]
    state = result["state"]
    timekeeper = result["timekeeper"]
    try:
        duration = float(timekeeper.total())
    except Exception:  # noqa: BLE001 - timing is advisory; never break the view
        duration = 0.0
    if duration < 0:
        duration = 0.0
    category = getattr(status.category, "value", "") or ""
    outcome = getattr(getattr(status, "outcome", None), "name", "") or ""
    spec_id = result["id"]
    return JobView(
        id=spec_id,
        short_id=spec_id[:8],
        name=result["spec_name"],
        fullname=result["spec_fullname"],
        file_path=result["file_path"],
        phase=state.phase.name,
        status=category,
        status_label=status.display_name(),
        status_markup=status.display_name(style="rich"),
        status_glyph=status.glyph(),
        category=category,
        outcome=outcome,
        reason=status.reason or "",
        duration=duration,
        session=str(result["session"]),
    )


def list_jobs(ids: list[str] | None = None, include_upstreams: bool = False) -> list[JobView]:
    """Return a list of :class:`JobView` for the current workspace.

    Each entry is the latest result for a spec, projected to primitives and
    sorted by name.  Interfaces render these directly; the DB is never touched
    by the caller.
    """
    results = get_results(ids, include_upstreams=include_upstreams)
    views = [_job_view(r) for r in results.values()]
    views.sort(key=lambda v: (v["name"], v["short_id"]))
    return views


def job_history(spec_id: str) -> list[JobView]:
    """Return every historical result for *spec_id* as :class:`JobView`, oldest first."""
    return [_job_view(r) for r in get_result_history(spec_id)]


def job_log(spec_id: str, *, stream: str = "stdout") -> str:
    """Return a job's captured *stream* output as text (empty if none).

    A thin pass-through to the application facade so interfaces read job output
    through the same ``canary.app`` surface as everything else, never touching
    the workspace layout directly.
    """
    return get_job_log(spec_id, stream=stream)


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
    info = get_workspace_info()
    return WorkspaceSummary(
        root=str(info.get("root", "")),
        session_count=int(info.get("session_count", 0)),
        latest_session=str(info.get("latest_session") or ""),
        spec_count=len(info.get("specs", []) or []),
        tags=list(info.get("tags", []) or []),
        version=str(info.get("version", "")),
    )


def status_counts(views: list[JobView]) -> dict[str, int]:
    """Tally :class:`JobView` rows by status category (for a summary line)."""
    counts: dict[str, int] = {}
    for v in views:
        key = v["status"] or "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
    return counts
