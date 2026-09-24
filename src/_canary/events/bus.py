# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Typed events and a minimal synchronous in-process event bus."""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import Callable
from typing import Literal

# ``job_submitted`` .. ``job_died`` are the names the execution layer emits
# today (see the ``queue.put({"event": ...})`` sites in ``queue_executor`` and
# ``runtest`` and the HPC backend).  ``job_blocked`` / ``job_cancelled``
# correspond to real state transitions (``Job.blocked_by_dependency``,
# ``ResourceQueue.clear``) that are not yet surfaced as wire events but need a
# stable name.  Any new emitted string must be added here.
EventName = Literal[
    "session_started",
    "session_finished",
    "job_submitted",
    "job_staged",
    "job_started",
    "job_stopped",
    "job_updated",
    "job_finished",
    "job_timeout",
    "job_died",
    "job_blocked",
    "job_cancelled",
]

#: Job-lifecycle event names a healthy job passes through, in order.  Must
#: remain a superset of ``queue_executor.EventTypes`` so no emitted event is
#: unrepresentable on the bus.
JOB_LIFECYCLE_EVENTS: tuple[str, ...] = (
    "job_submitted",
    "job_staged",
    "job_started",
    "job_stopped",
    "job_finished",
)


@dataclasses.dataclass(frozen=True)
class Event:
    """An immutable record that something happened.

    ``payload`` carries event-specific data; for job events it typically holds
    the job (or ``ExecutionSlot``) and a timestamp, mirroring the dict payloads
    used by the current protocol.
    """

    name: str
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)


Subscriber = Callable[[Event], None]


class EventBus:
    """Synchronous, single-process publish/subscribe hub.

    Delivery is synchronous and in registration order, matching
    ``ResourceQueueExecutor.notify_listeners``.  Subscribers registered for a
    specific name receive only that event; subscribers registered with
    ``name=None`` receive every event.  Name-specific subscribers are notified
    before global ones.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, list[Subscriber]] = {}
        self._global: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber, *, name: str | None = None) -> Subscriber:
        """Register *subscriber*, returning it so this may be used as a decorator.

        With ``name`` set, only events of that name are delivered; otherwise the
        subscriber receives all events.
        """
        if name is None:
            self._global.append(subscriber)
        else:
            self._by_name.setdefault(name, []).append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber, *, name: str | None = None) -> None:
        """Remove a previously registered *subscriber*; a no-op if not present."""
        bucket = self._global if name is None else self._by_name.get(name, [])
        try:
            bucket.remove(subscriber)
        except ValueError:  # nosec B110
            pass

    def publish(self, event: Event) -> None:
        """Deliver *event* to matching name subscribers, then global subscribers."""
        for sub in list(self._by_name.get(event.name, ())):
            sub(event)
        for sub in list(self._global):
            sub(event)

    def emit(self, name: str, /, **payload: Any) -> Event:
        """Build an :class:`Event` and :meth:`publish` it."""
        event = Event(name=name, payload=dict(payload))
        self.publish(event)
        return event
