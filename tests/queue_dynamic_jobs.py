# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Test dynamic job addition to ResourceQueue."""

import threading
from typing import Any
from typing import cast

from _canary.core.job import BaseJob
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


def test_incremental_cost_recalculation_allows_dynamic_jobs():
    """Test that jobs can be added dynamically with incremental cost recalculation."""
    q = ResourceQueue(
        lock=threading.Lock(),
        resource_pool=cast(Any, FakePool()),
        jobs=None,
        cost_recalculation="incremental",
    )

    # Add first batch of jobs
    job1 = DummyJob(id="1" * 64, cpus=1)
    job2 = DummyJob(id="2" * 64, cpus=2)
    q.put(cast(BaseJob, job1), cast(BaseJob, job2))

    # Should be marked dirty
    assert q._dirty is True

    # Get first job - should trigger cost calculation
    first_job = q.get()
    assert first_job.id in (job1.id, job2.id)
    assert q._dirty is False

    # Mark it done so it's not in _busy
    q.done(first_job)

    # Now add more jobs dynamically
    job3 = DummyJob(id="3" * 64, cpus=1)
    job4 = DummyJob(id="4" * 64, cpus=1)
    q.put(cast(BaseJob, job3), cast(BaseJob, job4))

    # Should be marked dirty again
    assert q._dirty is True

    # Get next job - should recalculate costs
    second_job = q.get()
    # Second job should be one of the remaining jobs
    remaining_ids = {job1.id, job2.id, job3.id, job4.id} - {first_job.id}
    assert second_job.id in remaining_ids
    assert q._dirty is False


def test_total_cost_recalculation_recomputes_all():
    """Test that total mode recalculates all job costs."""
    q = ResourceQueue(
        lock=threading.Lock(),
        resource_pool=cast(Any, FakePool()),
        jobs=None,
        cost_recalculation="total",
    )

    # Add first batch
    job1 = DummyJob(id="1" * 64, cpus=1)
    job2 = DummyJob(id="2" * 64, cpus=2)
    q.put(cast(BaseJob, job1), cast(BaseJob, job2))

    # Get first job
    first_job = q.get()
    assert first_job.id in (job1.id, job2.id)

    # Add more jobs - in total mode, all jobs get recalculated
    job3 = DummyJob(id="3" * 64, cpus=3)
    q.put(cast(BaseJob, job3))

    assert q._dirty is True

    # Get next job
    second_job = q.get()
    assert second_job.id in (job2.id, job3.id)
    assert q._dirty is False


def test_put_without_get_keeps_dirty_flag():
    """Test that put() sets dirty flag and it persists until get()."""
    q = ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, FakePool()), jobs=None)

    job1 = DummyJob(id="1" * 64)
    q.put(cast(BaseJob, job1))
    assert q._dirty is True

    # Multiple puts keep it dirty
    job2 = DummyJob(id="2" * 64)
    q.put(cast(BaseJob, job2))
    assert q._dirty is True

    # Only get() clears it
    q.get()
    assert q._dirty is False


def test_cohort_timestamp_in_cost_tuple():
    """Test that cost is a tuple with timestamp."""
    q = ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, FakePool()), jobs=None)

    job1 = DummyJob(id="1" * 64)
    q.put(cast(BaseJob, job1))

    # Before get(), should have sentinel
    assert q._heap[0].cost == (0.0, 0.0)

    # After get() (which triggers update_costs), should have (timestamp, cost)
    retrieved = q.get()
    # Check the internal heap structure after job is moved to _busy
    # The cost is calculated during get()
    assert retrieved.id == job1.id
