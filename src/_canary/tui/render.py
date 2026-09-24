# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Pure rendering for the Canary explorer TUI.

Every function here takes plain data (``JobView`` rows, an
:class:`~_canary.tui.state.ExplorerState`, a workspace summary) and returns a
Rich renderable.  There is no I/O and no application access, so frames can be
rendered and asserted on in tests without a terminal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from ..app.queries import JobView
    from ..app.queries import WorkspaceSummary
    from .state import ExplorerState

_HELP = "[dim]j/k move · g/G top/bottom · enter detail · f filter · a all · q quit[/dim]"


def _fmt_duration(seconds: float) -> str:
    """Format a duration in seconds as ``H:MM:SS`` / ``M:SS`` / ``S.s``."""
    if seconds <= 0:
        return "-"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    if m:
        return f"{m}:{sec:02d}"
    return f"{seconds:.1f}s"


def render_header(summary: "WorkspaceSummary", counts: dict[str, int]) -> Panel:
    """Render the workspace summary and per-status tallies as a header panel."""
    line = Text()
    line.append(summary["root"], style="bold")
    line.append(f"   specs: {summary['spec_count']}", style="dim")
    line.append(f"   sessions: {summary['session_count']}", style="dim")
    if summary["latest_session"]:
        line.append(f"   latest: {summary['latest_session']}", style="dim")
    tally = Text()
    if counts:
        for i, (status, n) in enumerate(sorted(counts.items())):
            if i:
                tally.append("  ")
            tally.append(f"{status}={n}")
    else:
        tally.append("no results yet", style="dim")
    return Panel(Group(line, tally), title="canary", title_align="left")


def render_table(state: "ExplorerState") -> Table:
    """Render the visible job rows, highlighting the selected one."""
    table = Table(expand=True)
    table.add_column("", width=1, no_wrap=True)  # cursor marker
    table.add_column("Job", ratio=3, no_wrap=True)
    table.add_column("ID", width=8, no_wrap=True)
    table.add_column("Status", width=18, no_wrap=True)
    table.add_column("Phase", width=10, no_wrap=True)
    table.add_column("Time", width=8, justify="right", no_wrap=True)

    rows = state.visible_jobs
    if not rows:
        table.add_row("", Text("no matching jobs", style="dim"), "", "", "", "")
        return table

    selected_idx = min(state.cursor, len(rows) - 1)
    for i, job in enumerate(rows):
        marker = "›" if i == selected_idx else " "
        name = Text(job["name"])
        row_style = "reverse" if i == selected_idx else None
        table.add_row(
            marker,
            name,
            job["short_id"],
            Text.from_markup(job["status_markup"]),
            job["phase"],
            _fmt_duration(job["duration"]),
            style=row_style,
        )
    return table


def render_detail(job: "JobView") -> Panel:
    """Render the detail pane for a single selected job."""
    body = Text()
    body.append("id       ", style="dim")
    body.append(f"{job['id']}\n")
    body.append("name     ", style="dim")
    body.append(f"{job['fullname']}\n")
    body.append("file     ", style="dim")
    body.append(f"{job['file_path']}\n")
    body.append("status   ", style="dim")
    body.append(Text.from_markup(job["status_markup"]))
    body.append("\n")
    body.append("phase    ", style="dim")
    body.append(f"{job['phase']}\n")
    body.append("duration ", style="dim")
    body.append(f"{_fmt_duration(job['duration'])}\n")
    body.append("session  ", style="dim")
    body.append(f"{job['session']}")
    if job["reason"]:
        body.append("\nreason   ", style="dim")
        body.append(job["reason"])
    return Panel(body, title="detail", title_align="left")


def render_footer(state: "ExplorerState") -> Text:
    """Render the status/help footer line."""
    parts = Text()
    filt = state.status_filter or "all"
    parts.append(f"filter: {filt}", style="bold")
    rows = state.visible_jobs
    if rows:
        parts.append(f"   {min(state.cursor, len(rows) - 1) + 1}/{len(rows)}", style="dim")
    parts.append("   ")
    parts.append(Text.from_markup(_HELP))
    return parts


def render_frame(
    state: "ExplorerState", summary: "WorkspaceSummary", counts: dict[str, int]
) -> Group:
    """Compose the full explorer frame (header, table, optional detail, footer)."""
    parts: list[RenderableType] = [render_header(summary, counts), render_table(state)]
    if state.show_detail and state.selected is not None:
        parts.append(render_detail(state.selected))
    parts.append(render_footer(state))
    return Group(*parts)
