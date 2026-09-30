# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Live progress tracking for a run observed by the TUI.

While an in-place rerun executes in a child process, its job-lifecycle events
stream onto the application event bus (see :mod:`_canary.events`).  This module
accumulates those events into a small, thread-safe tally the runner can render
as a progress bar without querying the database on every frame.

:class:`RunProgress` is deliberately event-sourced and advisory: it reflects
what the event stream has reported so far.  The database remains the source of
truth for final results (the runner still calls
:meth:`~_canary.tui.app.ExplorerModel.refresh` on completion); this tracker just
makes the *in-flight* picture immediate.

The tracker is updated from the event-publisher thread and read from the render
thread, so every access is guarded by a lock.  A snapshot
(:class:`RunProgressView`) is taken under the lock and handed to the pure
renderer, keeping rendering free of shared mutable state.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import Event


@dataclass(frozen=True)
class RunProgressView:
    """An immutable snapshot of run progress for rendering.

    Attributes:
        total: Best-known total number of jobs in the run (``0`` if unknown yet).
        finished: Number of jobs that have reported a terminal event.
        running: Number of jobs currently executing (started, not yet finished).
        by_status: Count of finished jobs keyed by status category
            (e.g. ``{"PASS": 3, "FAIL": 1}``).
        elapsed: Seconds since the run began.
        active: Whether a run is currently being tracked.
    """

    total: int
    finished: int
    running: int
    by_status: dict[str, int]
    elapsed: float
    active: bool

    @property
    def pending(self) -> int:
        """Jobs neither finished nor currently running (may be approximate)."""
        return max(0, self.total - self.finished - self.running)

    @property
    def fraction(self) -> float:
        """Completed fraction in ``[0, 1]`` (``0`` when the total is unknown)."""
        if self.total <= 0:
            return 0.0
        return min(1.0, self.finished / self.total)


#: Event names that mark a job as terminal (no longer running).
_TERMINAL_EVENTS = frozenset({"job_finished", "job_timeout", "job_died", "job_cancelled"})
#: Event name that marks a job as actively running.
_START_EVENT = "job_started"


class RunProgress:
    """Thread-safe, event-sourced tally of an in-flight run.

    Call :meth:`begin` when a run starts, feed it every :class:`~_canary.events.Event`
    via :meth:`on_event` (safe to call from the publisher thread), and read a
    consistent :meth:`snapshot` from the render thread.  :meth:`end` stops
    tracking.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._started_at = 0.0
        self._total = 0
        self._running: set[str] = set()
        self._finished: set[str] = set()
        self._by_status: dict[str, int] = {}
        #: Last-seen flat payload for each currently-running job, so a cancel can
        #: synthesize a terminal ``job_cancelled`` event with the job's identity
        #: (see :meth:`running_jobs`).  Keyed by job id.
        self._running_payloads: dict[str, dict] = {}

    def begin(self, total: int = 0) -> None:
        """Start tracking a new run, resetting all tallies.

        *total* is an optional hint; the tracker also learns the total from the
        ``qsize`` field carried on job events, so a caller that does not know the
        count up front can pass ``0``.
        """
        with self._lock:
            self._active = True
            self._started_at = time.monotonic()
            self._total = max(0, total)
            self._running.clear()
            self._finished.clear()
            self._by_status.clear()
            self._running_payloads.clear()

    def end(self) -> None:
        """Stop tracking; :meth:`snapshot` will report ``active=False``."""
        with self._lock:
            self._active = False

    def on_event(self, event: "Event") -> None:
        """Fold a single job-lifecycle event into the tally (publisher-thread safe).

        Ignores events when no run is being tracked.  Uses the flat
        :class:`~_canary.events.JobEvent` payload under ``event.payload['job']``;
        tolerates a missing/partial payload so it never raises on the hot path.
        """
        job = event.payload.get("job") if event.payload else None
        job_id = job.get("id") if isinstance(job, dict) else None
        with self._lock:
            if not self._active:
                return
            # Learn the run size from the queue size reported on events.
            if isinstance(job, dict):
                qsize = job.get("qsize", -1)
                if isinstance(qsize, int) and qsize > self._total:
                    self._total = qsize
            if job_id is None:
                return
            if event.name == _START_EVENT:
                self._running.add(job_id)
                if isinstance(job, dict):
                    self._running_payloads[job_id] = dict(job)
            elif event.name in _TERMINAL_EVENTS:
                self._running.discard(job_id)
                self._running_payloads.pop(job_id, None)
                if job_id not in self._finished:
                    self._finished.add(job_id)
                    status = ""
                    if isinstance(job, dict):
                        status = str(job.get("status") or "") or "DONE"
                    self._by_status[status] = self._by_status.get(status, 0) + 1

    def snapshot(self) -> RunProgressView:
        """Return an immutable, consistent view of the current progress."""
        with self._lock:
            elapsed = (time.monotonic() - self._started_at) if self._active else 0.0
            return RunProgressView(
                total=self._total,
                finished=len(self._finished),
                running=len(self._running),
                by_status=dict(self._by_status),
                elapsed=elapsed,
                active=self._active,
            )

    def running_jobs(self) -> list[dict]:
        """Flat payloads of jobs that started but have not reported a terminal event.

        Returned as a copy under the lock so a caller (the cancel path) can
        synthesize ``job_cancelled`` events for exactly the jobs that were still
        in flight when the run was stopped.
        """
        with self._lock:
            return [dict(p) for p in self._running_payloads.values()]
