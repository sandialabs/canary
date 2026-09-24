# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The Canary explorer TUI runner.

This is the only module in :mod:`_canary.tui` that performs I/O.  It is a thin
interface adapter: it pulls render-ready rows from the application query
surface (:mod:`_canary.app.queries`), feeds the pure
:class:`~_canary.tui.state.ExplorerState`, and draws frames with
:class:`rich.live.Live`.  It contains no business logic -- all workspace access
goes through ``_canary.app``.

Keyboard input is read from the terminal in raw mode on a background thread so
the display can also refresh on a timer (picking up results a running session
spools to the database).  When stdin is not a TTY the loop degrades to a single
rendered frame, which keeps it usable in tests and pipelines.
"""

from __future__ import annotations

import contextlib
import queue
import sys
import threading
import time
from typing import TYPE_CHECKING

from rich.console import Console
from rich.live import Live

from ..app import queries
from .render import render_frame
from .state import ExplorerState

if TYPE_CHECKING:
    from ..app.queries import JobView
    from ..app.queries import WorkspaceSummary
    from ..events import Event
    from ..events import EventBus


class ExplorerModel:
    """Bridges the application query surface to the pure UI state.

    Kept separate from the runner so it can be exercised without a terminal.

    When :meth:`subscribe` is given an :class:`~_canary.events.EventBus`, job
    events flip a thread-safe *dirty* flag; the runner polls
    :meth:`consume_dirty` so a live session's progress is reflected promptly
    without waiting for the periodic timer.  Event delivery only marks the model
    dirty -- the authoritative rows still come from :meth:`refresh` (the DB),
    keeping the database the source of truth.
    """

    def __init__(self) -> None:
        self.state = ExplorerState()
        self._dirty = threading.Event()
        self._bus: "EventBus | None" = None

    def refresh(self) -> None:
        """Pull the latest job rows from the application into the UI state."""
        self.state.update_jobs(self.fetch_jobs())

    def subscribe(self, bus: "EventBus") -> None:
        """Subscribe to *bus*; any job event marks the model dirty for refresh."""
        self._bus = bus
        bus.subscribe(self._on_event)

    def unsubscribe(self) -> None:
        """Detach from the event bus, if subscribed."""
        if self._bus is not None:
            self._bus.unsubscribe(self._on_event)
            self._bus = None

    def _on_event(self, event: "Event") -> None:
        # Runs on the publisher's thread; only sets a flag (no query/render I/O).
        self._dirty.set()

    def consume_dirty(self) -> bool:
        """Return whether an event arrived since the last call, clearing the flag."""
        if self._dirty.is_set():
            self._dirty.clear()
            return True
        return False

    # These thin wrappers exist so tests can subclass/patch the data source.
    def fetch_jobs(self) -> "list[JobView]":
        return queries.list_jobs()

    def fetch_summary(self) -> "WorkspaceSummary":
        return queries.workspace_summary()

    def fetch_log(self, spec_id: str) -> str:
        return queries.job_log(spec_id)

    def open_selected_log(self) -> None:
        """Fetch the selected job's log and switch the state into log mode.

        This is the model's single log-related I/O point; the pure state machine
        holds the resulting text but never reads the workspace itself.
        """
        job = self.state.selected
        if job is None:
            return
        text = self.fetch_log(job["id"])
        self.state.open_log(f"{job['name']}  ({job['short_id']})", text)

    def counts(self) -> dict[str, int]:
        return queries.status_counts(self.state.jobs)

    def frame(self):
        """Render the current model to a Rich renderable."""
        return render_frame(self.state, self.fetch_summary(), self.counts())


def _read_keys(stop: threading.Event, out: "queue.Queue[str]") -> None:
    """Read single key presses from a raw-mode TTY onto *out* until *stop* is set.

    Arrow keys and Page keys arrive as escape sequences and are normalised to
    the logical names :meth:`ExplorerState.handle_key` understands.
    """
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while not stop.is_set():
            import select as _select

            r, _, _ = _select.select([sys.stdin], [], [], 0.2)
            if not r:
                continue
            ch = sys.stdin.read(1)
            if ch == "\x1b":  # escape or an escape sequence
                seq = _read_escape_sequence()
                out.put(seq)
            else:
                out.put(ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_escape_sequence() -> str:
    """Resolve a pending ANSI escape sequence to a logical key name."""
    import select as _select

    r, _, _ = _select.select([sys.stdin], [], [], 0.05)
    if not r:
        return "escape"
    b1 = sys.stdin.read(1)
    if b1 != "[":
        return "escape"
    b2 = sys.stdin.read(1)
    return {
        "A": "up",
        "B": "down",
        "C": "right",
        "D": "left",
        "H": "home",
        "F": "end",
        "5": "pageup",
        "6": "pagedown",
    }.get(b2, "escape")


def run(
    *, console: Console | None = None, refresh_interval: float = 2.0, once: bool = False
) -> int:
    """Launch the explorer TUI over the current workspace.

    Args:
        console: Rich console to draw on (defaults to a fresh stderr console).
        refresh_interval: Seconds between automatic data refreshes.
        once: Render a single frame and return (used for non-interactive
            environments and tests).

    Returns:
        Process exit code (``0``).
    """
    console = console or Console(stderr=True)
    model = ExplorerModel()
    model.subscribe(queries.get_event_bus())
    model.refresh()

    interactive = (not once) and sys.stdin.isatty() and console.is_terminal
    if not interactive:
        console.print(model.frame())
        model.unsubscribe()
        return 0

    keys: "queue.Queue[str]" = queue.Queue()
    stop = threading.Event()
    reader = threading.Thread(target=_read_keys, args=(stop, keys), daemon=True)
    reader.start()

    last_refresh = time.monotonic()
    try:
        with Live(model.frame(), console=console, screen=True, auto_refresh=False) as live:
            while not model.state.quit:
                dirty = False
                # Size the table window to the terminal so rows never spill off
                # the bottom; recomputed each frame so it tracks resizes.
                model.state.set_viewport_height(_body_height(console, model.state))
                with contextlib.suppress(queue.Empty):
                    while True:
                        key = keys.get_nowait()
                        # Enter/space in list mode is a request to view the log,
                        # which is I/O -- the model performs it, not the state.
                        if model.state.wants_log(key):
                            model.open_selected_log()
                            dirty = True
                        elif model.state.handle_key(key):
                            dirty = True
                now = time.monotonic()
                # Refresh on a job event (live session progress) or the timer,
                # whichever comes first; both re-read authoritative rows from the DB.
                if model.consume_dirty() or now - last_refresh >= refresh_interval:
                    model.refresh()
                    last_refresh = now
                    dirty = True
                if dirty:
                    live.update(model.frame(), refresh=True)
                else:
                    time.sleep(0.05)
    finally:
        model.unsubscribe()
        stop.set()
        reader.join(timeout=1.0)
    return 0


# Non-body chrome rendered around the scrollable region: header panel (border +
# two content lines + border) and, in list mode, the footer line.  Detail pane,
# when open, consumes further rows; a conservative reserve keeps the cursor row
# on screen rather than fighting for an exact count.
_LIST_CHROME = 5
_DETAIL_CHROME = 8
_LOG_CHROME = 6


def _body_height(console: Console, state: "ExplorerState") -> int:
    """Rows available for the scrollable region given the console height."""
    total = console.size.height
    if state.mode == "log":
        reserve = _LOG_CHROME
    elif state.show_detail:
        reserve = _DETAIL_CHROME
    else:
        reserve = _LIST_CHROME
    return max(1, total - reserve)
