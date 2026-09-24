# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the durable, file-system-backed event channel (``events.spool``).

The spool bus streams events from a run in another process back to an observing
parent's :class:`~_canary.events.EventBus`, reusing the deadlock-free
``FSQueue``/``ResultListener`` pattern.  These tests pin the round trip over a
real temp directory (the true transport), a burst of events, and stop
semantics (a final drain so trailing events are not lost).
"""

import time

from _canary.events import Event
from _canary.events import EventBus
from _canary.events import SpoolBus
from _canary.events import SpoolListener


def _drain_until(pred, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_spool_bus_publishes_records_readable_by_listener(tmp_path):
    spool = tmp_path / "events"
    parent_bus = EventBus()
    seen: list[Event] = []
    parent_bus.subscribe(seen.append)

    listener = SpoolListener(spool, parent_bus)
    listener.start()
    try:
        producer = SpoolBus(spool)
        producer.publish(Event(name="job_started", payload={"job": {"id": "1"}}))
        producer.publish(Event(name="job_finished", payload={"job": {"id": "1"}}))
        assert _drain_until(lambda: len(seen) >= 2)
    finally:
        listener.stop()

    assert [e.name for e in seen] == ["job_started", "job_finished"]
    assert seen[0].payload == {"job": {"id": "1"}}


def test_spool_bus_forward_is_a_bus_subscriber(tmp_path):
    """SpoolBus.forward can be subscribed directly to a producer-side bus."""
    spool = tmp_path / "events"
    producer_bus = EventBus()
    producer_bus.subscribe(SpoolBus(spool).forward)

    producer_bus.emit("job_started", job={"id": "7"})

    parent_bus = EventBus()
    seen: list[Event] = []
    parent_bus.subscribe(seen.append)
    listener = SpoolListener(spool, parent_bus)
    listener.start()
    try:
        assert _drain_until(lambda: len(seen) == 1)
    finally:
        listener.stop()
    assert seen[0].name == "job_started"
    assert seen[0].payload == {"job": {"id": "7"}}


def test_listener_final_drain_delivers_trailing_events(tmp_path):
    """Events written just before stop() must still be delivered (final drain)."""
    spool = tmp_path / "events"
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(seen.append)

    # Write before the listener even starts; the first drain must pick them up.
    producer = SpoolBus(spool)
    for i in range(5):
        producer.publish(Event(name="job_finished", payload={"i": i}))

    listener = SpoolListener(spool, bus)
    listener.start()
    listener.stop()  # stop immediately; the final drain must flush the spool

    assert _drain_until(lambda: len(seen) == 5)
    assert {e.payload["i"] for e in seen} == set(range(5))


def test_listener_tolerates_malformed_record(tmp_path):
    spool = tmp_path / "events"
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(seen.append)

    # Put a raw non-tuple record straight onto the underlying FSQueue.
    SpoolBus(spool)._queue.put("not-a-tuple")
    SpoolBus(spool).publish(Event(name="job_started", payload={"id": "9"}))

    listener = SpoolListener(spool, bus)
    listener.start()
    try:
        assert _drain_until(lambda: len(seen) == 1)
    finally:
        listener.stop()
    assert seen[0].name == "job_started"
