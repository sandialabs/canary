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
from typing import Literal

if TYPE_CHECKING:
    from ..app.queries import JobView


@dataclass
class ExplorerState:
    """Selection, filtering, scrolling, and detail state for the job explorer.

    Attributes:
        jobs: The most recent full list of job rows from the application.
        cursor: Index of the highlighted row within the *filtered* view.
        top: Index of the first visible row -- the scroll offset that keeps the
            cursor inside a window of ``viewport_height`` rows.
        viewport_height: Rows the table body can show; the runner sets this from
            the terminal height each frame.  0 means "unbounded" (show all).
        status_filter: When set, only rows whose ``status`` equals this are shown.
        show_detail: Whether the detail pane for the selected row is open.
        mode: ``"list"`` (the job table) or ``"log"`` (a single job's output).
        log_lines: The selected job's log split into lines, in log mode.
        log_top: Scroll offset (first visible line) within the log.
        log_title: Header text for the log pane (job name/stream).
        marked_ids: Spec ids the user has marked (multi-select) for a bulk
            action such as rerun; independent of the cursor.
        rerun_requested: Edge-triggered flag the runner consumes to launch a
            rerun of the marked jobs (or the cursor row when none are marked).
        edit_requested: Edge-triggered flag the runner consumes to open the
            cursor row's test file in an editor.
        cancel_requested: Edge-triggered flag the runner consumes to cancel an
            in-flight run (set by ``esc``/``q`` while :attr:`running`).
        running: Whether an in-place rerun is currently executing (shown in the
            footer); set by the runner, cleared when the run finishes.
        quit: Set by :meth:`handle_key` when the user asks to exit.
    """

    jobs: list["JobView"] = field(default_factory=list)
    cursor: int = 0
    top: int = 0
    viewport_height: int = 0
    status_filter: str | None = None
    show_detail: bool = False
    mode: Literal["list", "log"] = "list"
    log_lines: list[str] = field(default_factory=list)
    log_top: int = 0
    log_title: str = ""
    marked_ids: set[str] = field(default_factory=set)
    rerun_requested: bool = False
    edit_requested: bool = False
    cancel_requested: bool = False
    running: bool = False
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
        self._scroll_into_view()

    # -- derived views ------------------------------------------------------

    @property
    def visible_jobs(self) -> list["JobView"]:
        """The rows currently shown, after applying :attr:`status_filter`."""
        if self.status_filter is None:
            return self.jobs
        return [j for j in self.jobs if j["status"] == self.status_filter]

    def window(self) -> list["JobView"]:
        """The slice of :attr:`visible_jobs` that fits the current viewport.

        With ``viewport_height <= 0`` the whole filtered list is returned; this
        keeps single-frame/``--once`` rendering and tests unbounded.
        """
        rows = self.visible_jobs
        if self.viewport_height <= 0:
            return rows
        return rows[self.top : self.top + self.viewport_height]

    @property
    def window_cursor(self) -> int:
        """Cursor position relative to the top of the visible window."""
        return min(self.cursor, len(self.visible_jobs) - 1) - self.top

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
        self._scroll_into_view()

    def move_home(self) -> None:
        self.cursor = 0
        self._scroll_into_view()

    def move_end(self) -> None:
        rows = self.visible_jobs
        self.cursor = max(0, len(rows) - 1)
        self._scroll_into_view()

    def set_viewport_height(self, height: int) -> None:
        """Set the visible row count (from the terminal) and re-scroll if needed."""
        self.viewport_height = max(0, height)
        self._scroll_into_view()

    def set_filter(self, status: str | None) -> None:
        """Set (or clear with ``None``) the status filter and reset the cursor."""
        self.status_filter = status
        self.cursor = 0
        self.top = 0

    def toggle_detail(self) -> None:
        self.show_detail = not self.show_detail

    # -- multi-select -------------------------------------------------------

    def toggle_mark(self) -> None:
        """Add/remove the cursor row's spec id from the marked set."""
        sid = self.selected_id
        if sid is None:
            return
        if sid in self.marked_ids:
            self.marked_ids.discard(sid)
        else:
            self.marked_ids.add(sid)

    def clear_marks(self) -> None:
        """Unmark all rows."""
        self.marked_ids.clear()

    def is_marked(self, spec_id: str) -> bool:
        return spec_id in self.marked_ids

    def rerun_target_ids(self) -> list[str]:
        """Spec ids a rerun would act on: the marked set, or the cursor row.

        Marks may reference jobs no longer present (a refresh dropped them), so
        the marked set is intersected with the current rows; when nothing valid
        is marked, the single cursor row is the target.
        """
        present = {j["id"] for j in self.jobs}
        marked = [j["id"] for j in self.jobs if j["id"] in self.marked_ids and j["id"] in present]
        if marked:
            return marked
        sid = self.selected_id
        return [sid] if sid is not None else []

    def consume_rerun_request(self) -> list[str]:
        """Return the rerun target ids if a rerun was requested, else an empty list.

        Edge-triggered: clears the request flag so the runner acts on it once.
        """
        if not self.rerun_requested:
            return []
        self.rerun_requested = False
        return self.rerun_target_ids()

    def consume_edit_request(self) -> str | None:
        """Return the cursor row's file path if an edit was requested, else ``None``.

        Edge-triggered: clears the request flag so the runner acts on it once.
        """
        if not self.edit_requested:
            return None
        self.edit_requested = False
        row = self.selected
        return row["file_path"] if row is not None else None

    def consume_cancel_request(self) -> bool:
        """Return whether a run cancellation was requested, clearing the flag.

        Edge-triggered: the runner acts on it once (terminating the child run),
        mirroring :meth:`consume_rerun_request` / :meth:`consume_edit_request`.
        """
        if not self.cancel_requested:
            return False
        self.cancel_requested = False
        return True

    def _clamp_cursor(self) -> None:
        rows = self.visible_jobs
        self.cursor = 0 if not rows else max(0, min(self.cursor, len(rows) - 1))

    def _scroll_into_view(self) -> None:
        """Adjust :attr:`top` so the cursor stays within the visible window."""
        rows = self.visible_jobs
        if self.viewport_height <= 0 or not rows:
            self.top = 0
            return
        cursor = min(self.cursor, len(rows) - 1)
        if cursor < self.top:
            self.top = cursor
        elif cursor >= self.top + self.viewport_height:
            self.top = cursor - self.viewport_height + 1
        # Keep the window full when scrolled near the end.
        max_top = max(0, len(rows) - self.viewport_height)
        self.top = min(self.top, max_top)

    # -- log mode -----------------------------------------------------------

    def open_log(self, title: str, text: str) -> None:
        """Enter log mode showing *text* (under header *title*) from the top."""
        self.mode = "log"
        self.log_title = title
        self.log_lines = text.splitlines() or ["(no output)"]
        self.log_top = 0

    def close_log(self) -> None:
        """Return to the job list."""
        self.mode = "list"
        self.log_lines = []
        self.log_top = 0

    def scroll_log(self, delta: int) -> None:
        """Scroll the log by *delta* lines, clamped, keeping a page on screen."""
        height = self.viewport_height if self.viewport_height > 0 else len(self.log_lines)
        max_top = max(0, len(self.log_lines) - max(1, height))
        self.log_top = max(0, min(self.log_top + delta, max_top))

    # -- key handling -------------------------------------------------------

    def handle_key(self, key: str) -> bool:
        """Apply a single key press; return ``True`` if it changed state.

        In log mode ``j/k`` (and arrows/page keys) scroll the log and
        ``enter``/``escape``/``q`` return to the list.  In list mode:

        * ``j`` / down arrow -- move down;   ``k`` / up arrow -- move up
        * ``g`` -- top;   ``G`` -- bottom;   pageup/pagedown -- by window
        * ``enter`` / ``space`` -- open the selected job's log
        * ``d`` -- toggle the inline detail pane
        * ``x`` -- mark/unmark the row for rerun (and advance)
        * ``c`` -- clear all marks
        * ``r`` -- rerun the marked rows (or the cursor row if none marked)
        * ``e`` -- edit the cursor row's test file
        * ``a`` -- clear the status filter (show all)
        * ``f`` -- cycle the status filter through the statuses present
        * ``q`` / ``escape`` -- cancel the in-flight run if one is running,
          otherwise quit
        """
        if self.mode == "log":
            return self._handle_key_log(key)
        return self._handle_key_list(key)

    def _handle_key_list(self, key: str) -> bool:
        if key in ("q", "Q", "escape"):
            # While a run is in flight, q/escape cancels it (edge-triggered flag
            # the runner consumes) rather than quitting the TUI; the user quits
            # once the run has settled.  The runner does the actual (I/O) cancel.
            if self.running:
                self.cancel_requested = True
                return True
            self.quit = True
            return True
        if key in ("j", "down"):
            self.move(1)
            return True
        if key in ("k", "up"):
            self.move(-1)
            return True
        if key in ("pagedown",):
            self.move(self._page())
            return True
        if key in ("pageup",):
            self.move(-self._page())
            return True
        if key == "g":
            self.move_home()
            return True
        if key == "G":
            self.move_end()
            return True
        if key in ("enter", "\r", "\n", " ", "space"):
            # The runner performs the log fetch (I/O) when it sees log_request.
            return self.selected is not None
        if key in ("d", "D"):
            self.toggle_detail()
            return True
        if key in ("a", "A"):
            self.set_filter(None)
            return True
        if key in ("f", "F"):
            self._cycle_filter()
            return True
        if key in ("x", "X"):
            self.toggle_mark()
            self.move(1)  # marking advances, so a run of rows is quick to select
            return True
        if key in ("c", "C"):
            self.clear_marks()
            return True
        if key in ("r", "R"):
            # The runner performs the actual run (heavy I/O) when it observes
            # the request; the state only records intent, doing no I/O itself.
            if self.rerun_target_ids():
                self.rerun_requested = True
                return True
            return False
        if key in ("e", "E"):
            # Editing is I/O (spawns $EDITOR); the runner does it, the state
            # only records intent.  Requires a cursor row with a file.
            row = self.selected
            if row is not None and row.get("file_path"):
                self.edit_requested = True
                return True
            return False
        return False

    def _handle_key_log(self, key: str) -> bool:
        if key in ("q", "Q", "escape", "enter", "\r", "\n"):
            self.close_log()
            return True
        if key in ("j", "down"):
            self.scroll_log(1)
            return True
        if key in ("k", "up"):
            self.scroll_log(-1)
            return True
        if key in ("pagedown", " ", "space"):
            self.scroll_log(self._page())
            return True
        if key == "pageup":
            self.scroll_log(-self._page())
            return True
        if key == "g":
            self.log_top = 0
            return True
        if key == "G":
            self.scroll_log(len(self.log_lines))
            return True
        return False

    def wants_log(self, key: str) -> bool:
        """Whether *key* in list mode should open the selected job's log.

        The runner uses this to know when to perform the (I/O) log fetch, since
        the state machine itself does no I/O.
        """
        return (
            self.mode == "list"
            and key in ("enter", "\r", "\n", " ", "space")
            and self.selected is not None
        )

    def _page(self) -> int:
        """A page step: the viewport height, or a sane default when unbounded."""
        return self.viewport_height if self.viewport_height > 0 else 10

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
