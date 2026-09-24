# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the in-process event bus (``_canary.events``).

Pin the delivery semantics (ordering, name filtering, idempotent removal) the
execution layer relies on, and reconcile the canonical event names against the
strings the executor emits so the two cannot drift apart.
"""

import dataclasses

import pytest

from _canary.events import Event
from _canary.events import EventBus
from _canary.events.bus import JOB_LIFECYCLE_EVENTS
from _canary.execution.queue_executor import EventTypes


def test_name_subscriber_receives_only_matching_events():
    bus = EventBus()
    seen: list[Event] = []
    bus.subscribe(seen.append, name="job_started")

    bus.emit("job_started", job="x")
    bus.emit("job_finished", job="x")

    assert [e.name for e in seen] == ["job_started"]
    assert seen[0].payload == {"job": "x"}


def test_global_subscriber_receives_every_event():
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.name))

    bus.emit("job_submitted")
    bus.emit("job_started")
    bus.emit("job_finished")

    assert seen == ["job_submitted", "job_started", "job_finished"]


def test_name_subscribers_run_before_global_and_in_registration_order():
    bus = EventBus()
    order: list[str] = []
    bus.subscribe(lambda e: order.append("name1"), name="job_started")
    bus.subscribe(lambda e: order.append("name2"), name="job_started")
    bus.subscribe(lambda e: order.append("global"))

    bus.emit("job_started")

    assert order == ["name1", "name2", "global"]


def test_unsubscribe_stops_delivery_and_tolerates_repeat_removal():
    bus = EventBus()
    seen: list[Event] = []
    sub = bus.subscribe(seen.append, name="job_started")

    bus.unsubscribe(sub, name="job_started")
    bus.unsubscribe(sub, name="job_started")
    bus.emit("job_started")

    assert seen == []


def test_events_are_immutable():
    """Events are facts that have occurred; they must not be mutated after creation."""
    event = Event(name="job_started", payload={"a": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.name = "job_finished"  # type: ignore[misc]


def test_canonical_names_cover_every_executor_event():
    """The bus must be able to represent every event the executor emits."""
    executor_names = set(getattr(EventTypes, "__args__", ()))
    assert executor_names, "expected EventTypes to be a Literal with names"
    assert executor_names.issubset(set(JOB_LIFECYCLE_EVENTS))
