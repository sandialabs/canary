# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for ``canary_hpc.queue.ResourceQueue`` cancellation semantics."""

import heapq
import threading
from typing import Any
from typing import cast

from _canary.job import JobPhase
from _canary.job import JobState
from _canary.queue import HeapSlot
from _canary.status import Status
from canary_hpc.queue import ResourceQueue


class FakeChildJob:
    """Minimal child job: the object a batch iterates over and persists."""

    def __init__(self, id: str, *, outcome: str | None = None) -> None:
        self.id = id
        self.status = Status(outcome=outcome) if outcome is not None else Status()
        self.state = JobState(phase=JobPhase.DONE if outcome is not None else JobPhase.PENDING)
        self.saved = False

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(category=category, outcome=outcome, reason=reason, code=code)

    def save(self) -> None:
        self.saved = True


class FakeBatch:
    """Minimal TestBatch stand-in: iterable over children, own state/status."""

    def __init__(self, id: str, jobs: list[FakeChildJob]) -> None:
        self.id = id
        self.jobs = jobs
        self.state = JobState()
        self.status = Status()
        self.saved = False

    def __iter__(self):
        return iter(self.jobs)

    def cost(self) -> float:
        return 1.0

    def required_resources(self):
        return []

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.status.set(category=category, outcome=outcome, reason=reason, code=code)

    def save(self, children: bool = True) -> None:
        self.saved = True
        if children:
            for job in self.jobs:
                job.save()


class FakePool:
    def accommodates(self, req) -> bool:
        return True


def _make_queue() -> ResourceQueue:
    return ResourceQueue(lock=threading.Lock(), resource_pool=cast(Any, FakePool()), jobs=None)


def _push(q: ResourceQueue, batch: FakeBatch) -> None:
    heapq.heappush(q._heap, HeapSlot(job=cast(Any, batch)))


def test_clear_propagates_interrupt_to_child_jobs() -> None:
    """Interrupting a pending batch must cancel its children, not leave NONE (NONE)."""
    children = [FakeChildJob(f"job-{i}") for i in range(3)]
    batch = FakeBatch("batch-1", children)
    q = _make_queue()
    _push(q, batch)

    q.clear("INTERRUPTED", reason="Keyboard interrupt")

    assert len(q._heap) == 0
    # Batch itself is terminal.
    assert batch.state.is_done()
    assert batch.status.outcome.name == "INTERRUPTED"
    assert batch.saved
    # Every child job is terminal with a real, non-NONE status.
    for job in children:
        assert job.state.is_done()
        assert job.status.outcome.name == "INTERRUPTED"
        assert job.status.category.value == "ABORTED"
        assert not job.status.is_unset()
        assert "Keyboard interrupt" in (job.status.reason or "")
        assert job.saved


def test_clear_default_cancelled_reason_for_children() -> None:
    child = FakeChildJob("job-1")
    batch = FakeBatch("batch-1", [child])
    q = _make_queue()
    _push(q, batch)

    q.clear("CANCELLED")

    assert child.state.is_done()
    assert child.status.outcome.name == "CANCELLED"
    assert child.status.category.value == "ABORTED"
    assert "cancelled" in (child.status.reason or "").lower()


def test_clear_preserves_already_finished_children() -> None:
    """Children that already have a terminal result are not overwritten."""
    done = FakeChildJob("done", outcome="SUCCESS")
    pending = FakeChildJob("pending")
    batch = FakeBatch("batch-1", [done, pending])
    q = _make_queue()
    _push(q, batch)

    q.clear("INTERRUPTED", reason="Keyboard interrupt")

    # The finished child keeps its PASS result.
    assert done.status.outcome.name == "SUCCESS"
    # The pending child is cancelled.
    assert pending.status.outcome.name == "INTERRUPTED"
    assert pending.state.is_done()
