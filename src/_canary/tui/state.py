# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Pure UI state for the Canary explorer TUI.

This module holds no I/O: it is a small, fully testable state machine over a
list of :class:`~_canary.app.queries.JobView` rows.  The runner
(:mod:`_canary.tui.app`) feeds it fresh rows from the application query surface
and translates key presses into method calls; the renderer
(:mod:`_canary.tui.render`) reads it to draw a frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app.queries import JobView


@dataclass
class ExplorerState:
    """Selection, filtering, and detail state for the job explorer.

    Attributes:
        jobs: The most recent full list of job rows from the application.
        cursor: Index of the highlighted row within the *filtered* view.
        status_filter: When set, only rows whose ``status`` equals this are shown.
        show_detail: Whether the detail pane for the selected row is open.
        quit: Set by :meth:`handle_key` when the user asks to exit.
    """

    jobs: list["JobView"] = field(default_factory=list)
    cursor: int = 0
    status_filter: str | None = None
    show_detail: bool = False
    quit: bool = False

    # -- data updates -------------------------------------------------------

    def update_jobs(self, jobs: list["JobView"]) -> None:
        """Replace the job list, keeping the cursor on the same spec id if possible."""
        prior_id = self.selected_id
        self.jobs = jobs
        if prior_id is not None:
            for i, row in enumerate(self.visible_jobs):
                if row["id"] == prior_id:
                    self.cursor = i
                    break
            else:
                self._clamp_cursor()
        else:
            self._clamp_cursor()

    # -- derived views ------------------------------------------------------

    @property
    def visible_jobs(self) -> list["JobView"]:
        """The rows currently shown, after applying :attr:`status_filter`."""
        if self.status_filter is None:
            return self.jobs
        return [j for j in self.jobs if j["status"] == self.status_filter]

    @property
    def selected(self) -> "JobView | None":
        """The currently highlighted row, or ``None`` when the view is empty."""
        rows = self.visible_jobs
        if not rows:
            return None
        idx = min(self.cursor, len(rows) - 1)
        return rows[idx]

    @property
    def selected_id(self) -> str | None:
        """Spec id of the highlighted row, or ``None``."""
        row = self.selected
        return row["id"] if row is not None else None

    # -- movement -----------------------------------------------------------

    def move(self, delta: int) -> None:
        """Move the cursor by *delta* rows, clamped to the visible range."""
        rows = self.visible_jobs
        if not rows:
            self.cursor = 0
            return
        self.cursor = max(0, min(self.cursor + delta, len(rows) - 1))

    def move_home(self) -> None:
        self.cursor = 0

    def move_end(self) -> None:
        rows = self.visible_jobs
        self.cursor = max(0, len(rows) - 1)

    def set_filter(self, status: str | None) -> None:
        """Set (or clear with ``None``) the status filter and reset the cursor."""
        self.status_filter = status
        self.cursor = 0

    def toggle_detail(self) -> None:
        self.show_detail = not self.show_detail

    def _clamp_cursor(self) -> None:
        rows = self.visible_jobs
        self.cursor = 0 if not rows else max(0, min(self.cursor, len(rows) - 1))

    # -- key handling -------------------------------------------------------

    def handle_key(self, key: str) -> bool:
        """Apply a single key press; return ``True`` if it changed state.

        Recognised keys (case-insensitive where sensible):

        * ``j`` / down arrow -- move down;   ``k`` / up arrow -- move up
        * ``g`` -- top;   ``G`` -- bottom
        * ``enter`` / ``space`` -- toggle the detail pane
        * ``a`` -- clear the status filter (show all)
        * ``f`` -- cycle the status filter through the statuses present
        * ``q`` / ``escape`` -- quit
        """
        if key in ("q", "Q", "escape"):
            self.quit = True
            return True
        if key in ("j", "down"):
            self.move(1)
            return True
        if key in ("k", "up"):
            self.move(-1)
            return True
        if key in ("pagedown",):
            self.move(10)
            return True
        if key in ("pageup",):
            self.move(-10)
            return True
        if key == "g":
            self.move_home()
            return True
        if key == "G":
            self.move_end()
            return True
        if key in ("enter", "\r", "\n", " ", "space"):
            self.toggle_detail()
            return True
        if key in ("a", "A"):
            self.set_filter(None)
            return True
        if key in ("f", "F"):
            self._cycle_filter()
            return True
        return False

    def _cycle_filter(self) -> None:
        """Advance the status filter to the next distinct status (then to 'all')."""
        statuses = sorted({j["status"] for j in self.jobs if j["status"]})
        if not statuses:
            return
        if self.status_filter is None:
            self.set_filter(statuses[0])
            return
        try:
            idx = statuses.index(self.status_filter)
        except ValueError:
            self.set_filter(statuses[0])
            return
        if idx + 1 >= len(statuses):
            self.set_filter(None)  # wrap back to "all"
        else:
            self.set_filter(statuses[idx + 1])
