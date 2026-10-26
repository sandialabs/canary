# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Resource queue checkout timeout propagation."""

from __future__ import annotations

import threading
from typing import Any

from _canary.execution.queue import ResourceQueue
from _canary.resource_pool.rpool import NodeRequest


class FakeJob:
    def __init__(self, *, checkout_timeout: float | None) -> None:
        self.id = "job-1"
        self.exclusive = False
        self._checkout_timeout = checkout_timeout
        self.assigned: dict[str, Any] | None = None

    @property
    def timeout(self) -> float:
        return 10.0

    def validate_enqueuable(self) -> None:
        return None

    def refresh_readiness(self) -> None:
        return None

    def is_runnable(self) -> bool:
        return True

    def is_ready(self) -> bool:
        return True

    def save(self) -> None:
        return None

    def assign_resources(self, allocation: dict[str, Any]) -> None:
        self.assigned = allocation

    def required_resources(self) -> list[NodeRequest]:
        req = NodeRequest()
        req.add("cpus", 1)
        return [req]

    def resource_checkout_timeout(self) -> float | None:
        return self._checkout_timeout


class FakeResourcePool:
    def __init__(self) -> None:
        self.calls: list[tuple[list[NodeRequest], dict[str, Any]]] = []

    def accommodates(self, resources: list[NodeRequest]) -> bool:
        return True

    def count(self, resource_type: str) -> int:
        assert resource_type == "cpus"
        return 1

    def checkout(self, resources: list[NodeRequest], **kwds: Any) -> dict[str, Any]:
        self.calls.append((resources, kwds))
        return {"metadata": {}, "resources": {}}


def test_resource_queue_passes_checkout_timeout_when_job_requests_it() -> None:
    rpool = FakeResourcePool()
    queue = ResourceQueue(threading.Lock(), resource_pool=rpool)
    job = FakeJob(checkout_timeout=321.0)

    queue.put(job)
    queue.prepare()
    queue.get()

    resources, kwds = rpool.calls[0]
    assert resources[0].count("cpus") == 1
    assert kwds == {"timeout": 321.0}


def test_resource_queue_omits_checkout_timeout_by_default() -> None:
    rpool = FakeResourcePool()
    queue = ResourceQueue(threading.Lock(), resource_pool=rpool)
    job = FakeJob(checkout_timeout=None)

    queue.put(job)
    queue.prepare()
    queue.get()

    resources, kwds = rpool.calls[0]
    assert resources[0].count("cpus") == 1
    assert kwds == {}
