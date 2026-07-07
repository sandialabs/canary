# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any

from _canary.status import Status
from _canary.testexec import ExecutionSpace
from _canary.timekeeper import Timekeeper
from canary_hpc.batchspec import BatchSpec
from canary_hpc.batchspec import TestBatch as HPCBatch


class FakeWorkspace:
    session = "fake-session"


class FakeState:
    def is_pending(self) -> bool:
        return True

    def is_running(self) -> bool:
        return False

    def is_done(self) -> bool:
        return False


class FakeJob:
    def __init__(
        self,
        *,
        id: str,
        cpus: int = 1,
        gpus: int = 0,
        runtime: float = 10.0,
    ) -> None:
        self.id = id
        self.cpus = cpus
        self.gpus = gpus
        self.runtime = runtime
        self.workspace = FakeWorkspace()
        self.status = Status()
        self.timekeeper = Timekeeper()
        self.state = FakeState()

    def __serialize__(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cpus": self.cpus,
            "gpus": self.gpus,
            "runtime": self.runtime,
        }

    def size(self) -> float:
        return float((self.cpus**2 + self.runtime**2) ** 0.5)

    def required_resources(self) -> list[dict[str, Any]]:
        request: list[dict[str, Any]] = []
        request.extend({"type": "cpus", "slots": 1} for _ in range(self.cpus))
        request.extend({"type": "gpus", "slots": 1} for _ in range(self.gpus))
        return request

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

    assert batch.allocation == {"metadata": {}, "resources": {}}
    assert batch.resources == {}
    assert batch.cpu_ids == []
    assert batch.gpu_ids == []


def test_batch_assign_resources_stores_full_allocation(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {
            "source": "test",
            "transaction_id": "abc123",
        },
        "resources": {
            "cpus": [
                {"node": "node0", "id": "0", "slots": 1},
                {"node": "node0", "id": "1", "slots": 1},
            ],
            "gpus": [
                {"node": "node0", "id": "0", "slots": 1},
            ],
        },
    }

    batch.assign_resources(allocation)

    assert batch.allocation == allocation
    assert batch.resources == allocation["resources"]
    assert batch.cpu_ids == ["0", "1"]
    assert batch.gpu_ids == ["0"]


def test_batch_assign_resources_deep_copies_allocation(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test"},
        "resources": {
            "cpus": [{"node": "node0", "id": "0", "slots": 1}],
        },
    }

    batch.assign_resources(allocation)

    allocation["metadata"]["source"] = "mutated"
    allocation["resources"]["cpus"][0]["id"] = "99"

    assert batch.allocation == {
        "metadata": {"source": "test"},
        "resources": {
            "cpus": [{"node": "node0", "id": "0", "slots": 1}],
        },
    }


def test_batch_free_resources_returns_full_allocation_and_clears_batch(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {
            "source": "distributed",
            "hostname": "worker01",
            "transaction_id": "abc123",
        },
        "resources": {
            "cpus": [{"node": "worker01", "id": "0", "slots": 1}],
        },
    }

    batch.assign_resources(allocation)

    returned = batch.free_resources()

    assert returned == allocation
    assert batch.allocation == {"metadata": {}, "resources": {}}
    assert batch.resources == {}


def test_batch_free_resources_returns_deep_copy(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "test"},
        "resources": {
            "cpus": [{"node": "node0", "id": "0", "slots": 1}],
        },
    }

    batch.assign_resources(allocation)

    returned = batch.free_resources()
    returned["metadata"]["source"] = "mutated"
    returned["resources"]["cpus"][0]["id"] = "99"

    assert batch.allocation == {"metadata": {}, "resources": {}}


def test_batch_setup_writes_allocation_to_lockfile(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {
            "source": "test",
            "transaction_id": "abc123",
        },
        "resources": {
            "cpus": [{"node": "node0", "id": "0", "slots": 1}],
        },
    }

    batch.assign_resources(allocation)
    batch.setup()

    data = batch.loadconfig(str(batch.workspace.dir))

    assert data["allocation"] == allocation
    assert data["id"] == batch.id
    assert data["session"] == batch.session
    assert data["jobs"] == ["job-1"]


def test_batch_required_resources_is_submission_resource_only(tmp_path):
    batch = make_batch(
        tmp_path,
        [
            FakeJob(id="job-1", cpus=4, gpus=1),
            FakeJob(id="job-2", cpus=2, gpus=0),
        ],
    )

    assert batch.required_resources() == [{"type": "cpus", "slots": 1}]
