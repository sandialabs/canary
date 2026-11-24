# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The TUI's job rows: the app's job record plus what the TUI needs to show it.

The application layer returns one job record for every interface
(:data:`_canary.app.queries.JobRecord`); the TUI flattens it and adds its display fields
(a short id, the status label, glyph and Rich markup) here.  Live job events
(:class:`~_canary.events.bus.JobEvent`) carry the same fields, so a row can be updated
from an event without a query.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import TypedDict

from ..core.status import Status


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
    """Absolute path to the test's source file (``file_root/file_path``).

    Stored split in the DB (a scan root plus a path relative to it), but joined
    here so interfaces get a path they can open or display directly, independent
    of the process's current working directory.
    """
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


def job_view(record: dict[str, Any], anchor: Path | str) -> JobView:
    """The TUI row for *record*; its ``file_path`` made absolute (the TUI opens it)."""
    status = record["status"]
    # The generator's absolute path, which the TUI opens: file_root / file_path.
    file_path = record["file_path"] or ""
    if file_path and record["file_root"]:
        file_path = str(Path(record["file_root"]) / file_path)
    elif file_path and not Path(file_path).is_absolute():
        file_path = str(Path(anchor) / file_path)
    if not record["session"]:  # collected, never run
        label, markup, glyph = "NOTRUN", "[dim]NOTRUN[/]", "○"
    else:
        s = Status.from_dict(
            {
                "category": status["category"],
                "outcome": status["outcome"],
                "reason": status["reason"],
            }
        )
        label, markup, glyph = s.display_name(), s.display_name(style="rich"), s.glyph()
    duration = record["duration"]
    return JobView(
        id=record["id"],
        short_id=record["id"][:8],
        name=record["name"],
        fullname=record["fullname"],
        file_path=file_path,
        phase=record["phase"],
        status=status["category"],
        status_label=label,
        status_markup=markup,
        status_glyph=glyph,
        category=status["category"],
        outcome="" if status["outcome"] == "NONE" and not record["session"] else status["outcome"],
        reason=status["reason"] or "",
        duration=float(duration) if duration is not None and duration >= 0 else 0.0,
        session=record["session"],
    )


def list_job_views() -> list[JobView]:
    """The TUI's rows for every collected job (see :func:`_canary.app.queries.list_jobs`)."""
    from ..app import queries
    from ..workspace.workspace import Workspace

    anchor = Workspace.load().root.parent
    return [job_view(record, anchor) for record in queries.list_jobs()]


def status_counts(views: list[JobView]) -> dict[str, int]:
    """Tally :class:`JobView` rows by status category (for a summary line)."""
    counts: dict[str, int] = {}
    for v in views:
        key = v["status"] or "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
    return counts
