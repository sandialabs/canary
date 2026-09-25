# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""A durable, file-system-backed event channel across process boundaries.

The in-process :class:`~_canary.events.bus.EventBus` delivers events only within
one process.  When a run executes in a *child* process (so it cannot fight an
observing interface for the terminal, the CWD, or signal handling) its events
must still reach the parent's bus, where interfaces such as the TUI subscribe.

This module carries events across that boundary using the same disk-backed queue
Canary already uses to funnel test results to the single database writer
(:class:`~_canary.util.multiprocessing.FSQueue`, drained by
:class:`~_canary.persistence.database.ResultListener`).  That pattern -- pickled
records written with an atomic rename, drained FIFO by a daemon thread -- is
deadlock-free across *fully independent* processes because a file has no
background feeder thread to flush (unlike :class:`multiprocessing.Queue`, whose
feeder blocks process exit until the parent drains it).

* :class:`SpoolBus` (producer side, any process) subscribes to an in-process
  bus -- or is written to directly -- and appends each event to the spool.  Only
  the event ``name`` and its primitives-only ``payload`` are stored, so nothing
  that cannot be pickled crosses the boundary.
* :class:`SpoolListener` (consumer side, the parent) is a daemon thread that
  drains the spool and republishes each event onto a local :class:`EventBus`,
  mirroring :class:`~_canary.persistence.database.ResultListener`.

The transport is agnostic to how the child process is launched.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

from ..util.multiprocessing import FSQueue
from .bus import Event

if TYPE_CHECKING:
    from .bus import EventBus


class SpoolBus:
    """Producer side: append events to a disk-backed spool directory.

    Safe to construct and write from any process, including a fully independent
    ``canary`` invocation, because :class:`~_canary.util.multiprocessing.FSQueue`
    stores each record as an atomically-renamed pickle file (multi-writer safe,
    no background feeder thread).
    """

    def __init__(self, directory: str | Path) -> None:
        self._queue = FSQueue(Path(directory))

    def publish(self, event: Event) -> None:
        """Append *event* (as a ``(name, payload)`` record) to the spool."""
        self._queue.put((event.name, event.payload))

    def forward(self, event: Event) -> None:
        """Bus-subscriber alias for :meth:`publish` (usable with ``bus.subscribe``)."""
        self.publish(event)


class SpoolListener:
    """Consumer side: drain a spool directory onto a local :class:`EventBus`.

    A daemon thread reads ``(name, payload)`` records written by a
    :class:`SpoolBus` in another process and republishes them onto *bus*, so
    local subscribers observe the child's events as if they were local.

    Modeled directly on :class:`~_canary.persistence.database.ResultListener`: a
    daemon thread whose whole job is to move items from a cross-process spool
    into an in-process sink, with a final drain after being asked to stop so no
    trailing events are lost.
    """

    def __init__(
        self, directory: str | Path, bus: "EventBus", *, poll_interval: float = 0.05
    ) -> None:
        self._queue = FSQueue(Path(directory))
        self._bus = bus
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background drain thread (idempotent)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="canary-event-spool", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._drain_once()
            time.sleep(self._poll_interval)
        # Final drain so events written just before stop are not lost.
        self._drain_once()

    def _drain_once(self) -> None:
        for item in self._queue.drain():
            self._publish(item)

    def _publish(self, item: object) -> None:
        # Tolerate a malformed record rather than kill the listener thread.
        if not isinstance(item, tuple) or len(item) != 2:
            return
        name, payload = item
        self._bus.publish(Event(name=cast(str, name), payload=cast(dict, payload or {})))

    def stop(self, *, timeout: float = 2.0) -> None:
        """Stop draining and join the thread; safe to call more than once."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
