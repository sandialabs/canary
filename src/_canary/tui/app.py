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
    from ..app.run_subprocess import RunHandle
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
        self._run: "RunHandle | None" = None

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

    def start_rerun(self, spec_ids: list[str]) -> "RunHandle":
        """Start an in-place rerun of *spec_ids* in a child process.

        Uses :func:`_canary.app.run_in_subprocess`, which runs the same
        ``app.run`` path as ``canary run <spec_id> ...`` (it computes the rerun
        closure itself) but in a separate process so the TUI keeps its live
        display, the terminal, and signal handling.  The child streams its
        job-lifecycle events back onto the application event bus this model is
        already subscribed to, so progress appears live without a console
        handoff.  Returns a :class:`~_canary.app.run_subprocess.RunHandle` the
        runner polls for completion.
        """
        from ..app.pathspec import SpecIdsRequest
        from ..app.run_subprocess import run_in_subprocess

        return run_in_subprocess(SpecIdsRequest(value=list(spec_ids)))

    @property
    def run_active(self) -> bool:
        """Whether an in-place rerun is currently executing."""
        return self._run is not None

    def begin_rerun(self, spec_ids: list[str]) -> bool:
        """Start an in-place rerun, unless one is already running.

        Returns ``True`` if a run was started.  The child streams events onto
        the bus this model subscribes to, so the runner's live loop repaints as
        progress arrives; the runner calls :meth:`poll_run` to detect completion.
        """
        if self._run is not None or not spec_ids:
            return False
        self._run = self.start_rerun(spec_ids)
        self.state.running = True
        return True

    def poll_run(self) -> bool:
        """Return ``True`` when a started run has finished, refreshing rows.

        Non-blocking.  On completion the run handle is cleared and the model is
        refreshed so the final results are shown; returns ``False`` while the
        run is still in flight or when no run is active.
        """
        if self._run is None:
            return False
        if self._run.poll() is None:
            return False
        self._run = None
        self.state.running = False
        self.refresh()
        return True

    #: The editor the TUI launches to edit a test file.  The TUI deliberately
    #: hardcodes ``vim`` rather than honoring ``$VISUAL``/``$EDITOR`` (as the CLI
    #: does): the TUI owns the full screen, and those variables frequently point
    #: at a GUI editor (e.g. ``code``) that would detach instead of blocking,
    #: making an in-terminal "edit" appear to do nothing.
    EDITOR = "vim"

    def edit_file(self, path: str) -> bool:
        """Open *path* in ``vim``, returning whether it changed on disk.

        The TUI uses ``vim`` directly (see :attr:`EDITOR`) instead of canary's
        environment-driven editor selection, so it never lands on a GUI editor
        that would detach.  The editor blocks, so the runner suspends the live
        display and hands over the terminal first; the mtime is compared so a
        rerun is offered only when the file actually changed.

        Returns ``False`` (a no-op) when the editor could not be launched.
        """
        # The TUI launches vim (not $EDITOR/$VISUAL) so it never lands on a GUI
        # editor that would detach from the terminal.
        import subprocess  # nosec B404

        p = Path(path)
        before = p.stat().st_mtime if p.exists() else None
        # Run the editor as a blocking child (not os.execv, which would replace
        # this process) and treat a clean exit as success.
        try:
            subprocess.run([self.EDITOR, str(p)], check=False)  # nosec B603
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

    # Interactive session: a live display that stays up across an in-place rerun
    # (the run executes in a child process and streams events back), and pauses
    # only to hand the terminal to an external editor.
    while True:
        action, payload = _live_session(console, model, refresh_interval)
        if action == "edit":
            # vim is full-screen: the live display and raw-mode reader are
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
        # action == "quit"
        model.unsubscribe()
        return 0


def _live_session(
    console: Console, model: "ExplorerModel", refresh_interval: float
) -> tuple[str, Any]:
    """Run the live display until the user quits or requests an editor.

    Returns ``(reason, payload)`` where *reason* is ``"quit"`` (payload
    ``None``) or ``"edit"`` (payload = file path).  A rerun does **not** end the
    session: it is launched in place (a child process, see
    :meth:`ExplorerModel.begin_rerun`) and the loop keeps drawing as the child's
    events arrive, until the run finishes.  The ``Live`` display and the
    raw-mode keyboard reader are fully torn down before returning, so the caller
    may safely run a full-screen external editor.
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
                if rerun_ids and model.begin_rerun(rerun_ids):
                    # In-place: the child streams events; keep drawing.  Clear
                    # any marks so the "running" set is unambiguous.
                    model.state.clear_marks()
                    dirty = True
                # A finished in-place run refreshes rows and clears the flag.
                if model.poll_run():
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
