# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Test dynamic job addition to ResourceQueue."""

import threading
from typing import Any
from typing import cast

import pytest

from _canary.core.job import BaseJob
from _canary.execution.queue import Empty
from _canary.execution.queue import ResourceQueue


class FakePool:
    def accommodates(self, req):
        return True

    def count(self, resource_type: str) -> int:
        assert resource_type == "cpus"
        return 4

    def checkout(self, resources, **kwds):
        return {"metadata": {}, "resources": {"cpus": [{"id": "0", "slots": 1, "node": "n0"}]}}

    def checkin(self, resources):
        pass


class DummyJob:
    def __init__(self, id: str, *, cpus: int = 1):
        self.id = id
        self.cpus_count = cpus
        self.timeout = 60.0  # Default timeout
        self.state = type("state", (), {"is_done": lambda: False})()
        self.status = type("status", (), {"category": "PASS", "outcome": "SUCCESS"})()
        self.exclusive = False

    def validate_enqueuable(self):
        pass

    def required_resources(self):
        from _canary.resource_pool.rpool import NodeRequest

        req = NodeRequest()
        req.add("cpus", self.cpus_count)
        return [req]

    def is_runnable(self):
        return True

    def is_ready(self):
        return True

    def refresh_readiness(self):
        pass

    def resource_checkout_timeout(self):
        return None

    def assign_resources(self, resources):
        pass

    def free_resources(self):
        return {"cpus": [{"id": "0", "slots": 1, "node": "n0"}]}


class TrackingLock:
    """threading.Lock stand-in that records whether it is held."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.held = False
        self.acquisitions = 0

    def __enter__(self):
        self._lock.acquire()
        self.held = True
        self.acquisitions += 1
        return self

    def __exit__(self, *exc):
        self.held = False
        self._lock.release()


def make_queue(lock=None) -> ResourceQueue:
    return ResourceQueue(lock=lock or threading.Lock(), resource_pool=cast(Any, FakePool()))


def job(name: str, cpus: int = 1) -> BaseJob:
    return cast(BaseJob, DummyJob(id=name * 64, cpus=cpus))


def drain(q: ResourceQueue) -> list[str]:
    order: list[str] = []
    while True:
        try:
            j = q.get()
        except Empty:
            return order
        order.append(j.id[0])
        q.done(j)


def test_priority_within_a_cohort():
    q = make_queue()
    q.put(job("a", cpus=1), job("b", cpus=3))
    assert drain(q) == ["b", "a"]


def test_jobs_added_after_get_are_scheduled_after_the_earlier_cohort():
    q = make_queue()
    q.put(job("a", cpus=1), job("b", cpus=2))
    first = q.get()
    q.done(first)
    assert first.id[0] == "b"
    # "c" has the highest priority, but "a" was queued in an earlier cohort.
    q.put(job("c", cpus=4), job("d", cpus=1))
    assert drain(q) == ["a", "c", "d"]


def test_empty_is_cleared_by_a_later_put():
    q = make_queue()
    q.put(job("a"))
    assert drain(q) == ["a"]
    with pytest.raises(Empty):
        q.get()
    q.put(job("b"))
    assert drain(q) == ["b"]


def test_costing_happens_under_the_same_lock_as_the_pop():
    """A put() between costing and popping must not let an uncosted slot jump the queue.

    Guaranteed when get() costs and pops within a single lock acquisition.
    """
    lock = TrackingLock()
    q = make_queue(lock=lock)
    seen: list[bool] = []
    original = q._cost_cohort

    def spy(slots):
        seen.append(lock.held)
        return original(slots)

    q._cost_cohort = spy  # type: ignore[method-assign]
    q.put(job("a"))
    before = lock.acquisitions
    q.get()
    assert seen == [True]
    assert lock.acquisitions - before == 1
