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

from rich.console import Console
from rich.console import Group
from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from ..app.queries import JobView
    from ..app.queries import WorkspaceSummary
    from .state import ExplorerState

_HELP = (
    "[dim]j/k move · enter log · x mark · r rerun · e edit · c clear · "
    "d detail · f filter · q quit[/dim]"
)
_LOG_HELP = "[dim]j/k scroll · g/G top/bottom · pgup/pgdn page · q/enter back[/dim]"

#: Rows a Rich table spends on its own frame regardless of body length: the top
#: border, the column-header row, the header/body separator, and the bottom
#: border.  Used to convert an available line budget into a row budget.
TABLE_FRAME_ROWS = 4


def measure_height(console: Console, renderable: RenderableType) -> int:
    """Return how many terminal lines *renderable* occupies at *console*'s width.

    Used by the runner to size the scrollable table to the space actually left
    by the (variable-height, wrapping) header/detail/footer, so the frame never
    exceeds the terminal height.
    """
    options = console.options.update(height=None)
    return len(console.render_lines(renderable, options, pad=False))


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
    """Render the visible job rows (the scrolled window).

    The first column shows the cursor (``›``); the second shows a mark
    (``✓``) for rows selected for a bulk action such as rerun.
    """
    table = Table(expand=True)
    table.add_column("", width=1, no_wrap=True)  # cursor marker
    table.add_column("", width=1, no_wrap=True)  # multi-select mark
    table.add_column("Job", ratio=3, no_wrap=True)
    table.add_column("ID", width=8, no_wrap=True)
    table.add_column("Status", width=18, no_wrap=True)
    table.add_column("Phase", width=10, no_wrap=True)
    table.add_column("Time", width=8, justify="right", no_wrap=True)

    rows = state.window()
    if not rows:
        table.add_row("", "", Text("no matching jobs", style="dim"), "", "", "", "")
        return table

    window_cursor = state.window_cursor
    for i, job in enumerate(rows):
        selected = i == window_cursor
        cursor_marker = "›" if selected else " "
        mark = Text("✓", style="bold cyan") if state.is_marked(job["id"]) else Text(" ")
        name = Text(job["name"])
        row_style = "reverse" if selected else None
        table.add_row(
            cursor_marker,
            mark,
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
    if state.running:
        parts.append("running… ", style="bold yellow")
    filt = state.status_filter or "all"
    parts.append(f"filter: {filt}", style="bold")
    rows = state.visible_jobs
    if rows:
        parts.append(f"   {min(state.cursor, len(rows) - 1) + 1}/{len(rows)}", style="dim")
    if state.marked_ids:
        parts.append(f"   marked: {len(state.marked_ids)}", style="bold cyan")
    parts.append("   ")
    parts.append(Text.from_markup(_HELP))
    return parts


def render_log(state: "ExplorerState") -> Group:
    """Render the log view: a scrolled window of the selected job's output."""
    height = state.viewport_height if state.viewport_height > 0 else len(state.log_lines)
    window = state.log_lines[state.log_top : state.log_top + height] if height else state.log_lines
    body = Text("\n".join(window) or "(no output)")
    total = len(state.log_lines)
    shown_end = min(state.log_top + len(window), total)
    footer = Text()
    footer.append(f"lines {state.log_top + 1}-{shown_end}/{total}", style="dim")
    footer.append("   ")
    footer.append(Text.from_markup(_LOG_HELP))
    return Group(Panel(body, title=state.log_title or "log", title_align="left"), footer)


def render_frame(
    state: "ExplorerState", summary: "WorkspaceSummary", counts: dict[str, int]
) -> Group:
    """Compose the full frame for the current mode.

    In ``list`` mode: header, scrolled job table, optional detail pane, footer.
    In ``log`` mode: the header plus the scrolled log view.
    """
    header = render_header(summary, counts)
    if state.mode == "log":
        return Group(header, render_log(state))
    parts: list[RenderableType] = [header, render_table(state)]
    if state.show_detail and state.selected is not None:
        parts.append(render_detail(state.selected))
    parts.append(render_footer(state))
    return Group(*parts)
