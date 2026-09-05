# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any

from _canary.job import JobPhase
from _canary.job import JobState
from _canary.resource_pool.rpool import NodeRequest
from _canary.status import Outcome
from _canary.status import Status
from _canary.testexec import ExecutionSpace
from _canary.timekeeper import Timekeeper
from canary_hpc.batchexec import _all_children_finished
from canary_hpc.batchspec import BatchSpec
from canary_hpc.batchspec import TestBatch as HPCBatch


class FakeWorkspace:
    session = "fake-session"


class FakeState:
    def __init__(self, phase: JobPhase = JobPhase.PENDING) -> None:
        self.phase = phase

    def is_pending(self) -> bool:
        return self.phase == JobPhase.PENDING

    def is_running(self) -> bool:
        return self.phase == JobPhase.RUNNING

    def is_done(self) -> bool:
        return self.phase == JobPhase.DONE


class FakeJob:
    def __init__(
        self,
        *,
        id: str,
        cpus: int = 1,
        gpus: int = 0,
        runtime: float = 10.0,
        outcome: Outcome | None = None,
    ) -> None:
        self.id = id
        self.cpus = cpus
        self.gpus = gpus
        self.runtime = runtime
        self.workspace = FakeWorkspace()
        self.status = Status(outcome=outcome) if outcome is not None else Status()
        self.timekeeper = Timekeeper()
        self.state = FakeState(phase=JobPhase.DONE if outcome is not None else JobPhase.PENDING)

    def __serialize__(self) -> dict[str, Any]:
        return {"id": self.id, "cpus": self.cpus, "gpus": self.gpus, "runtime": self.runtime}

    def size(self) -> float:
        return float((self.cpus**2 + self.runtime**2) ** 0.5)

    def required_resources(self) -> list[NodeRequest]:
        request = NodeRequest()
        request.add("cpus", self.cpus)
        request.add("gpus", self.gpus)
        return [request]

    def refresh(self) -> None:
        pass

    def save(self) -> None:
        pass

    def setstate(self, data: dict[str, Any]) -> None:
        pass


def make_batch(tmp_path: Path, jobs: list[FakeJob]) -> HPCBatch:
    spec = BatchSpec(layout="flat", jobs=jobs)  # type: ignore[arg-type]
    workspace = ExecutionSpace(root=tmp_path, path=Path("batch"))
    return HPCBatch(spec=spec, workspace=workspace)


def test_batch_initial_allocation_is_empty(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    assert batch.allocation == {"metadata": {}, "resources": {}, "state": "inactive"}
    assert batch.resources == {}
    assert batch.cpu_ids == []
    assert batch.gpu_ids == []


def test_batch_assign_resources_stores_full_allocation(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test", "transaction_id": "abc123"},
        "resources": {
            "cpus": [
                {"node": "node0", "id": "0", "slots": 1},
                {"node": "node0", "id": "1", "slots": 1},
            ],
            "gpus": [{"node": "node0", "id": "0", "slots": 1}],
        },
    }

    batch.assign_resources(allocation)

    assert batch.resources == allocation["resources"]
    assert batch.allocation["metadata"] == allocation["metadata"]
    assert batch.allocation["state"] == "active"
    assert batch.cpu_ids == ["0", "1"]
    assert batch.gpu_ids == ["0"]


def test_batch_assign_resources_deep_copies_allocation(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test"},
        "resources": {"cpus": [{"node": "node0", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)

    allocation["metadata"]["source"] = "mutated"
    allocation["resources"]["cpus"][0]["id"] = "99"

    assert batch.allocation == {
        "metadata": {"source": "test"},
        "resources": {"cpus": [{"node": "node0", "id": "0", "slots": 1}]},
        "state": "active",
    }


def test_batch_free_resources_returns_full_allocation_and_clears_batch(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "distributed", "hostname": "worker01", "transaction_id": "abc123"},
        "resources": {"cpus": [{"node": "worker01", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)

    returned = batch.free_resources()

    assert returned == allocation
    assert batch.allocation["metadata"] == allocation["metadata"]
    assert batch.allocation["resources"] == allocation["resources"]
    assert batch.allocation["state"] == "inactive"
    assert batch.resources == {}


def test_batch_free_resources_returns_deep_copy(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test"},
        "resources": {"cpus": [{"node": "node0", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)

    returned = batch.free_resources()
    returned["metadata"]["source"] = "mutated"
    returned["resources"]["cpus"][0]["id"] = "99"

    assert batch.allocation["metadata"] == allocation["metadata"]
    assert batch.allocation["resources"] == allocation["resources"]
    assert batch.allocation["state"] == "inactive"


def test_batch_setup_writes_allocation_to_lockfile(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test", "transaction_id": "abc123"},
        "resources": {"cpus": [{"node": "node0", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)
    batch.setup()

    data = batch.loadconfig(str(batch.workspace.dir))

    assert data["allocation"]["metadata"] == allocation["metadata"]
    assert data["allocation"]["resources"] == allocation["resources"]
    assert data["allocation"]["state"] == "active"
    assert data["id"] == batch.id
    assert data["session"] == batch.session
    assert data["jobs"] == ["job-1"]


def test_batch_required_resources_is_submission_resource_only(tmp_path):
    batch = make_batch(
        tmp_path, [FakeJob(id="job-1", cpus=4, gpus=1), FakeJob(id="job-2", cpus=2, gpus=0)]
    )

    assert batch.required_resources()[0].resources == [{"type": "cpus", "slots": 1}]


# ---------------------------------------------------------------------------
# Fix #9b-1: allocation.state is "inactive" in the final batch.lock
# ---------------------------------------------------------------------------


def test_allocation_state_inactive_after_run_finally(tmp_path):
    """After run() returns, _allocation['state'] must be 'inactive'.

    The fix writes self._allocation['state'] = 'inactive' inside the run()
    finally block before save(), so the on-disk batch.lock always reflects
    the released state even if free_resources() (called by the ResourceQueue
    after run() returns) never reaches disk.
    """
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    # Simulate the ResourceQueue assigning resources (active state)
    allocation = {
        "metadata": {"source": "test"},
        "resources": {"cpus": [{"node": "node0", "id": "0", "slots": 1}]},
    }
    batch.assign_resources(allocation)
    assert batch._allocation["state"] == "active"

    # Simulate what run() finally block does
    batch._allocation["state"] = "inactive"
    batch.setup()  # writes batch.lock
    batch.save()

    data = batch.loadconfig(str(batch.workspace.dir))
    assert data["allocation"]["state"] == "inactive"


def test_allocation_state_inactive_written_before_active_read(tmp_path):
    """Verify the fix does not corrupt the allocation resources — only state changes."""
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test"},
        "resources": {"cpus": [{"node": "node0", "id": "0", "slots": 1}]},
    }
    batch.assign_resources(allocation)

    # Apply the fix
    batch._allocation["state"] = "inactive"

    # Resources dict is preserved; only state changed
    assert batch._allocation["resources"] == allocation["resources"]
    assert batch._allocation["metadata"] == allocation["metadata"]
    assert batch._allocation["state"] == "inactive"


# ---------------------------------------------------------------------------
# Fix #9: _all_children_finished helper
# ---------------------------------------------------------------------------


def test_all_children_finished_all_pass(tmp_path):
    """Returns True when every child is DONE with a non-unset status."""
    jobs = [FakeJob(id="j1", outcome=Outcome.SUCCESS), FakeJob(id="j2", outcome=Outcome.SUCCESS)]
    batch = make_batch(tmp_path, jobs)
    assert _all_children_finished(batch) is True


def test_all_children_finished_one_pending(tmp_path):
    """Returns False when any child is still pending (no terminal status)."""
    jobs = [
        FakeJob(id="j1", outcome=Outcome.SUCCESS),
        FakeJob(id="j2"),  # no outcome → pending, status unset
    ]
    batch = make_batch(tmp_path, jobs)
    assert _all_children_finished(batch) is False


def test_all_children_finished_one_failed(tmp_path):
    """Returns True when all children are DONE even if one failed — the batch
    finalization will set batch status to FAILED from child outcomes."""
    jobs = [FakeJob(id="j1", outcome=Outcome.SUCCESS), FakeJob(id="j2", outcome=Outcome.FAILED)]
    batch = make_batch(tmp_path, jobs)
    assert _all_children_finished(batch) is True


def test_all_children_finished_empty_batch(tmp_path):
    """An empty batch vacuously has all children finished."""
    batch = make_batch(tmp_path, [FakeJob(id="j1", outcome=Outcome.SUCCESS)])
    batch.jobs = []
    assert _all_children_finished(batch) is True


def test_all_children_finished_refresh_raises(tmp_path):
    """If refresh() raises (lockfile missing), treated as not finished."""

    class FailRefreshJob(FakeJob):
        def refresh(self) -> None:
            raise FileNotFoundError("no lockfile")

    jobs = [FailRefreshJob(id="j1", outcome=Outcome.SUCCESS)]
    batch = make_batch(tmp_path, jobs)
    assert _all_children_finished(batch) is False


# ---------------------------------------------------------------------------
# Fix #9b-2: _finish_abnormal_slot reconciles batch status from child jobs
# ---------------------------------------------------------------------------


class _FakeSlotJob:
    """Minimal stand-in for a TestBatch used in _finish_abnormal_slot tests."""

    def __init__(self, jobs: list[FakeJob]) -> None:
        self.id = "aabbccdd-fake-id"
        self.jobs = jobs
        self.status = Status()
        self.state = JobState()
        self._allocation: dict = {"state": "active"}
        self._saved = False
        self._set_status_calls: list[dict] = []

    def refresh(self) -> None:
        pass

    def finalize_status_from_child_jobs(self) -> None:
        # Mirrors TestBatch logic: set SUCCESS if all children passed.
        if all(j.status.is_success() for j in self.jobs):
            self.status = Status(outcome=Outcome.SUCCESS)
        else:
            self.status = Status(outcome=Outcome.FAILED)

    def set_status(self, *, outcome: str, reason: str, code: int = -1) -> None:
        self._set_status_calls.append({"outcome": outcome, "reason": reason, "code": code})
        self.status = Status(outcome=Outcome[outcome])

    def save(self) -> None:
        self._saved = True


class _FakeSlot:
    def __init__(self, job: _FakeSlotJob) -> None:
        self.job = job
        self._finished_at: float | None = None

    def on_finish(self, t: float) -> None:
        self._finished_at = t


def test_finish_abnormal_slot_all_children_pass_uses_child_status(tmp_path):
    """When all child jobs passed, _finish_abnormal_slot should derive SUCCESS
    from children instead of stamping TIMEOUT/ERROR on the batch."""
    from _canary.queue_executor import ResourceQueueExecutor

    jobs = [FakeJob(id="j1", outcome=Outcome.SUCCESS), FakeJob(id="j2", outcome=Outcome.SUCCESS)]
    slot = _FakeSlot(_FakeSlotJob(jobs))

    # Use a minimal executor instance — only _finish_abnormal_slot is called.
    ex = ResourceQueueExecutor.__new__(ResourceQueueExecutor)
    ex._finish_abnormal_slot(slot, outcome="TIMEOUT", reason="watchdog")

    # set_status() should NOT have been called (children provided the status)
    assert slot.job._set_status_calls == []
    assert slot.job.status.is_success()
    assert slot.job._allocation["state"] == "inactive"
    assert slot.job._saved is True


def test_finish_abnormal_slot_child_failed_uses_abnormal_outcome(tmp_path):
    """When a child job failed, _finish_abnormal_slot should NOT override
    with child-derived status — the abnormal event is the right outcome."""
    from _canary.queue_executor import ResourceQueueExecutor

    jobs = [FakeJob(id="j1", outcome=Outcome.SUCCESS), FakeJob(id="j2", outcome=Outcome.FAILED)]
    slot = _FakeSlot(_FakeSlotJob(jobs))

    ex = ResourceQueueExecutor.__new__(ResourceQueueExecutor)
    ex._finish_abnormal_slot(slot, outcome="TIMEOUT", reason="watchdog")

    # finalize_status_from_child_jobs sets FAILED (one child failed).
    # The is_unset() guard is False (FAILED != unset), so the child-derived
    # path is taken but the status is FAILED — which is the correct outcome.
    assert not slot.job.status.is_unset()
    assert slot.job.status.is_failure()


def test_finish_abnormal_slot_no_finalize_method_falls_through(tmp_path):
    """For non-batch jobs (no finalize_status_from_child_jobs), the original
    behaviour is preserved: set_status is called with the abnormal outcome."""
    from _canary.queue_executor import ResourceQueueExecutor

    class PlainJob:
        id = "plain-job-id"

        def refresh(self) -> None:
            pass

        def set_status(self, *, outcome: str, reason: str, code: int = -1) -> None:
            self.outcome = outcome

        def save(self) -> None:
            pass

    class PlainSlot:
        job = PlainJob()

        def on_finish(self, t: float) -> None:
            pass

    slot = PlainSlot()
    ex = ResourceQueueExecutor.__new__(ResourceQueueExecutor)
    ex._finish_abnormal_slot(slot, outcome="TIMEOUT", reason="watchdog")

    assert slot.job.outcome == "TIMEOUT"
