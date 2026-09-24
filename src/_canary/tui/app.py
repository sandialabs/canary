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
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from rich.console import Console
from rich.live import Live

from ..app import queries
from .render import TABLE_FRAME_ROWS
from .render import measure_height
from .render import render_detail
from .render import render_footer
from .render import render_frame
from .render import render_header
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
        self._summary: "WorkspaceSummary | None" = None

    def refresh(self) -> None:
        """Pull the latest job rows and workspace summary into the UI state."""
        self.state.update_jobs(self.fetch_jobs())
        self._summary = self.fetch_summary()

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

    def rerun(self, spec_ids: list[str]) -> int:
        """Rerun the given jobs by spec id through the application layer.

        Uses the same ``app.run`` path as ``canary run <spec_id> ...``, which
        computes the rerun closure (upstream deps) itself.  Returns the run's
        exit code.  This is a heavy, blocking operation with its own console
        output, so the runner tears the live display down before calling it.
        """
        from ..app.pathspec import SpecIdsRequest
        from ..app.run import run as run_session

        return run_session(SpecIdsRequest(value=list(spec_ids)))

    def edit_file(self, path: str) -> bool:
        """Open *path* in the user's editor, returning whether it changed on disk.

        Resolves the editor from ``$VISUAL``/``$EDITOR`` (falling back to a
        common default) and blocks until it exits.  The editor is a full-screen
        program, so the runner suspends the live display and hands over the
        terminal before calling this.  The mtime is compared so the runner can
        offer to rerun only when the file was actually modified.
        """
        import os
        import shlex
        import subprocess  # nosec B404 - launching the user's own $EDITOR

        p = Path(path)
        before = p.stat().st_mtime if p.exists() else None
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        cmd = [*shlex.split(editor), str(p)]
        try:
            subprocess.run(cmd, check=False)  # nosec B603 - editor from user env
        except FileNotFoundError:
            return False
        after = p.stat().st_mtime if p.exists() else None
        return before != after

    def summary(self) -> "WorkspaceSummary":
        """The workspace summary cached at the last :meth:`refresh`.

        Cached so the runner can size the layout each frame (which needs the
        header height) without issuing an extra workspace query per frame.
        """
        if self._summary is None:
            self._summary = self.fetch_summary()
        return self._summary

    def frame(self):
        """Render the current model to a Rich renderable."""
        return render_frame(self.state, self.summary(), self.counts())


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

    # Interactive session: a live display that can pause to hand the terminal to
    # an external program (an editor) and resume, or exit to perform a rerun.
    while True:
        action, payload = _live_session(console, model, refresh_interval)
        if action == "edit":
            # $EDITOR is full-screen: the live display and raw-mode reader are
            # already torn down by _live_session before it returned.  Edit, then
            # loop back to re-enter the display with fresh data.
            changed = model.edit_file(payload)
            model.refresh()
            edited = model.state.selected
            if changed and edited is not None:
                # Offer an immediate rerun of the edited test by pre-marking it;
                # the user still confirms with 'r'.  Keeping it explicit avoids
                # surprising re-execution on every save.
                model.state.marked_ids = {edited["id"]}
            continue
        if action == "rerun":
            model.unsubscribe()
            # Display and raw-mode reader are down; the rerun owns the console.
            # (In-place/background rerun is future work; the selection + command
            # are identical, only the execution mechanism changes.)
            return model.rerun(payload)
        # action == "quit"
        model.unsubscribe()
        return 0


def _live_session(
    console: Console, model: "ExplorerModel", refresh_interval: float
) -> tuple[str, Any]:
    """Run the live display until the user quits or requests an action.

    Returns ``(reason, payload)`` where *reason* is ``"quit"`` (payload
    ``None``), ``"rerun"`` (payload = list of spec ids), or ``"edit"`` (payload =
    file path).  The ``Live`` display and the raw-mode keyboard reader are fully
    torn down before returning, so the caller may safely run a full-screen
    external program or a session with its own console output.
    """
    keys: "queue.Queue[str]" = queue.Queue()
    stop = threading.Event()
    reader = threading.Thread(target=_read_keys, args=(stop, keys), daemon=True)
    reader.start()

    reason: str = "quit"
    payload: Any = None
    last_refresh = time.monotonic()
    try:
        with Live(model.frame(), console=console, screen=True, auto_refresh=False) as live:
            while not model.state.quit:
                dirty = False
                # Size the scrollable region to the terminal so rows never spill
                # off the bottom; recomputed each frame so it tracks resizes.
                model.state.set_viewport_height(
                    _body_height(console, model.state, model.summary(), model.counts())
                )
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
                edit_path = model.state.consume_edit_request()
                if edit_path is not None:
                    reason, payload = "edit", edit_path
                    break
                rerun_ids = model.state.consume_rerun_request()
                if rerun_ids:
                    reason, payload = "rerun", rerun_ids
                    break
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
        stop.set()
        reader.join(timeout=1.0)
    return reason, payload


def _body_height(console: Console, state: "ExplorerState", summary, counts) -> int:
    """Rows the scrollable region can show after the real chrome is accounted for.

    The header/detail/footer wrap unpredictably (long workspace paths, narrow
    terminals), so their heights are *measured* at the current width rather than
    guessed; the scrollable region gets exactly the remaining lines.  This keeps
    the table (or log) filling down toward the bottom of the pane and makes it
    scroll once the cursor reaches the last visible row, instead of overrunning
    the terminal.
    """
    used = measure_height(console, render_header(summary, counts))
    if state.mode == "log":
        # Log view: a panel (top border, title, bottom border = 3) plus a footer
        # line under it; the panel body gets whatever remains.
        available = console.size.height - used - 4
        return max(1, available)
    used += measure_height(console, render_footer(state))
    if state.show_detail and state.selected is not None:
        used += measure_height(console, render_detail(state.selected))
    available = console.size.height - used - TABLE_FRAME_ROWS
    return max(1, available)
