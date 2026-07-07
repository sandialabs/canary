# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import threading
from typing import Any

from canary_dist.queue import ResourceQueue


class FakeResourcePool:
    def __init__(self) -> None:
        self.checked_in: list[dict[str, Any]] = []

    def checkin(self, allocation: dict[str, Any]) -> None:
        self.checked_in.append(allocation)


class FakeBatch:
    id = "batch-1"
    exclusive = False

    def __init__(self, allocation: dict[str, Any]) -> None:
        self._allocation = allocation

    def free_resources(self) -> dict[str, Any]:
        allocation = self._allocation
        self._allocation = {"metadata": {}, "resources": {}}
        return allocation


def test_queue_done_checkins_full_allocation():
    rpool = FakeResourcePool()
    q = ResourceQueue(threading.Lock(), resource_pool=rpool)  # type: ignore[arg-type]

    allocation = {
        "metadata": {"source": "distributed", "transaction_id": "tx-1"},
        "resources": {"cpus": [{"node": "host-a", "id": "0", "slots": 1}]},
    }

    batch = FakeBatch(allocation)
    q._busy[batch.id] = batch  # type: ignore[assignment]

    q.done(batch)  # type: ignore[arg-type]

    assert rpool.checked_in == [allocation]
    assert batch.id not in q._busy
    assert batch.id in q._finished
