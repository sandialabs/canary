# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any

from _canary.status import Status
from _canary.testexec import ExecutionSpace
from _canary.timekeeper import Timekeeper
from canary_dist.batchspec import TestBatch as DistBatch
from canary_hpc.batchspec import BatchSpec


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
    def __init__(self, *, id: str, cpus: int = 1, gpus: int = 0, runtime: float = 10.0) -> None:
        self.id = id
        self.cpus = cpus
        self.gpus = gpus
        self.runtime = runtime
        self.workspace = FakeWorkspace()
        self.status = Status()
        self.timekeeper = Timekeeper()
        self.state = FakeState()

    def __serialize__(self) -> dict[str, Any]:
        return {"id": self.id, "cpus": self.cpus, "gpus": self.gpus, "runtime": self.runtime}

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


def make_batch(tmp_path: Path, jobs: list[FakeJob]) -> DistBatch:
    spec = BatchSpec(layout="flat", jobs=jobs)  # type: ignore[arg-type]
    workspace = ExecutionSpace(root=tmp_path, path=Path("batch"))
    return DistBatch(spec=spec, workspace=workspace)


def test_assign_resources_extracts_distributed_metadata(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {
            "source": "distributed",
            "server_url": "http://server",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "resources": {"cpus": [{"node": "host-a", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)

    assert batch.hostname == "host-a"
    assert batch.transaction_id == "tx-1"
    assert batch.allocation == allocation


def test_assign_resources_derives_hostname_from_resources(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {"source": "distributed", "transaction_id": "tx-1"},
        "resources": {"cpus": [{"node": "host-a", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)

    assert batch.hostname == "host-a"
    assert batch.transaction_id == "tx-1"


def test_remote_resource_pool_is_single_node_batch_local_pool(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {
            "source": "distributed",
            "server_url": "http://server",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "resources": {
            "cpus": [
                {"node": "host-a", "id": "0", "slots": 1},
                {"node": "host-a", "id": "1", "slots": 1},
            ],
            "gpus": [{"node": "host-a", "id": "0", "slots": 1}],
        },
    }

    batch.assign_resources(allocation)

    assert batch.remote_resource_pool() == {
        "allow_multinode": False,
        "additional_properties": {
            "source": "distributed",
            "server_url": "http://server",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "nodes": [
            {
                "id": "host-a",
                "resources": {
                    "cpus": [{"id": "0", "slots": 1}, {"id": "1", "slots": 1}],
                    "gpus": [{"id": "0", "slots": 1}],
                },
            }
        ],
    }


def test_required_resources_uses_max_per_job_resources(tmp_path):
    batch = make_batch(
        tmp_path, [FakeJob(id="job-1", cpus=4, gpus=1), FakeJob(id="job-2", cpus=2, gpus=2)]
    )

    request = batch.required_resources()

    assert request.count({"type": "cpus", "slots": 1}) == 4
    assert request.count({"type": "gpus", "slots": 1}) == 2


def test_setup_writes_resource_pool_and_allocation(tmp_path):
    batch = make_batch(tmp_path, [FakeJob(id="job-1")])

    allocation = {
        "metadata": {
            "source": "distributed",
            "server_url": "http://server",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "resources": {"cpus": [{"node": "host-a", "id": "0", "slots": 1}]},
    }

    batch.assign_resources(allocation)
    batch.setup()

    data = DistBatch.loadconfig(str(batch.workspace.dir))

    assert data["allocation"] == allocation
    assert data["resource_pool"] == batch.remote_resource_pool()
    assert data["remote host"] == "host-a"
