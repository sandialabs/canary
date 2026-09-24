# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the cross-process event bridge (``_canary.events.bridge``).

The bridge lets a run executing in a child process stream its events back to an
observing parent's :class:`~_canary.events.EventBus`.  These tests pin the two
halves against a real :class:`multiprocessing.Queue` (in-process, but the true
transport type) so the pickling and end-of-stream semantics are exercised.
"""

import multiprocessing as mp

from _canary.events import Event
from _canary.events import EventBridge
from _canary.events import EventBus
from _canary.events import QueueForwarder


def _drain_until(pred, timeout=2.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_forwarder_puts_name_and_payload_on_queue():
    q: mp.Queue = mp.Queue()
    fwd = QueueForwarder(q)

    fwd.forward(Event(name="job_started", payload={"job": {"id": "abc"}}))

    name, payload = q.get(timeout=1.0)
    assert name == "job_started"
    assert payload == {"job": {"id": "abc"}}


def test_bridge_republishes_forwarded_events_onto_target_bus():
    """End-to-end: forwarder -> queue -> bridge -> parent bus subscriber."""
    q: mp.Queue = mp.Queue()
    parent_bus = EventBus()
    seen: list[Event] = []
    parent_bus.subscribe(seen.append)

    bridge = EventBridge(q, parent_bus)
    bridge.start()
    try:
        # Simulate a child process forwarding two events.
        fwd = QueueForwarder(q)
        fwd.forward(Event(name="job_started", payload={"job": {"id": "1"}}))
        fwd.forward(Event(name="job_finished", payload={"job": {"id": "1"}}))

        assert _drain_until(lambda: len(seen) >= 2)
    finally:
        bridge.stop()

    assert [e.name for e in seen] == ["job_started", "job_finished"]
    assert seen[0].payload == {"job": {"id": "1"}}


def test_bridge_stops_on_sentinel():
    q: mp.Queue = mp.Queue()
    bus = EventBus()
    bridge = EventBridge(q, bus)
    bridge.start()

    QueueForwarder(q).close()  # end-of-stream sentinel

    # After the sentinel the internal thread should have exited on its own.
    assert _drain_until(lambda: bridge._thread is not None and not bridge._thread.is_alive())
    bridge.stop()


def test_bridge_tolerates_malformed_item_without_dying():
    q: mp.Queue = mp.Queue()
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(seen.append)
    bridge = EventBridge(q, bus)
    bridge.start()
    try:
        q.put("not-a-tuple")  # malformed: must not kill the bridge
        q.put(("job_started", {"job": {"id": "9"}}))
        assert _drain_until(lambda: len(seen) == 1)
    finally:
        bridge.stop()

    assert seen[0].name == "job_started"
