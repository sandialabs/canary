# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Bridge :class:`~_canary.events.bus.Event` streams across a process boundary.

The in-process :class:`~_canary.events.bus.EventBus` delivers events only within
one process.  When a run executes in a *child* process (so it cannot fight the
observing interface for the terminal, the CWD, or signal handling) its events
must still reach the parent's bus, where interfaces such as the TUI subscribe.

This module provides the two halves of that bridge, built on a shared
:class:`multiprocessing.Queue`:

* :class:`QueueForwarder` (child side) subscribes to the child's bus and puts
  each :class:`~_canary.events.bus.Event` onto the queue.  Only the event
  ``name`` and its already-primitives-only ``payload`` cross the boundary, so
  the queue carries nothing that cannot be pickled.
* :class:`EventBridge` (parent side) is a daemon thread that drains the queue
  and republishes each event onto a target bus, mirroring the
  :class:`~_canary.persistence.database.ResultListener` daemon that drains the
  result spool into the database.

The transport is deliberately minimal: a single queue of ``(name, payload)``
tuples plus a ``None`` sentinel signalling end-of-stream.  It is agnostic to how
the child process is launched.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from typing import Any

from .bus import Event

if TYPE_CHECKING:
    from multiprocessing import Queue as MPQueue

    from .bus import EventBus


#: Put on the queue by :meth:`QueueForwarder.close` to tell an
#: :class:`EventBridge` the stream has ended so it can stop cleanly.
_SENTINEL = None


class QueueForwarder:
    """Child-side: forward a bus's events onto a cross-process queue.

    Subscribe :meth:`forward` to the child process's event bus; every published
    event is placed on *queue* as a ``(name, payload)`` tuple.  The payload is
    passed through unchanged -- job-lifecycle payloads are already
    primitives-only :class:`~_canary.events.bus.JobEvent` dicts, so the tuple is
    picklable and no ``_canary`` object crosses the boundary.
    """

    def __init__(self, queue: "MPQueue") -> None:
        self._queue = queue

    def forward(self, event: Event) -> None:
        """Enqueue *event* for the parent process (a bus subscriber callback)."""
        self._queue.put((event.name, event.payload))

    def close(self) -> None:
        """Signal end-of-stream so a draining :class:`EventBridge` can stop."""
        self._queue.put(_SENTINEL)


class EventBridge:
    """Parent-side: drain a cross-process queue onto a local :class:`EventBus`.

    A daemon thread reads ``(name, payload)`` tuples produced by a
    :class:`QueueForwarder` in another process and republishes them onto *bus*,
    so local subscribers observe the child's events as if they were local.  The
    thread exits when it reads the ``None`` sentinel or :meth:`stop` is called.

    Modeled on :class:`~_canary.persistence.database.ResultListener`: a daemon
    thread whose whole job is to move items from a cross-process queue into an
    in-process sink.
    """

    def __init__(self, queue: "MPQueue", bus: "EventBus", *, poll_interval: float = 0.05) -> None:
        self._queue = queue
        self._bus = bus
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background drain thread (idempotent)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="canary-event-bridge", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=self._poll_interval)
            except Exception:  # noqa: BLE001 - queue.Empty (or a closed queue at shutdown)
                continue
            if item is _SENTINEL:
                break
            self._publish(item)

    def _publish(self, item: Any) -> None:
        # Tolerate a malformed item rather than kill the bridge thread.
        try:
            name, payload = item
        except (TypeError, ValueError):
            return
        self._bus.publish(Event(name=name, payload=payload or {}))

    def stop(self, *, timeout: float = 1.0) -> None:
        """Stop draining and join the thread; safe to call more than once."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
