# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from collections import Counter
from typing import Any

import canary
import canary_hpc.batchspec as bs
from _canary.testexec import ExecutionSpace
from _canary.util.serialize import serialize

logger = canary.get_logger(__name__)


class TestBatch(bs.TestBatch):
    def __init__(self, spec: bs.BatchSpec, workspace: ExecutionSpace) -> None:
        super().__init__(spec=spec, workspace=workspace)
        self.hostname: str | None = None
        self.transaction_id: str | None = None
        self._cpus = max(job.cpus for job in self.jobs)
        self._gpus = max(job.gpus for job in self.jobs)

    def __str__(self) -> str:
        params = f"id={self.id[:7]}"
        if self.hostname is not None:
            params += f",host={self.hostname}"
        return f"batch[{params}]"

    @property
    def cpus(self) -> int:
        return self._cpus

    @cpus.setter
    def cpus(self, arg: int) -> None:
        self._cpus = arg

    @property
    def gpus(self) -> int:
        return self._gpus

    @gpus.setter
    def gpus(self, arg: int) -> None:
        self._gpus = arg

    def required_resources(self) -> list[dict[str, Any]]:
        # For distributed batches, request the maximum resources needed by any
        # single job in the batch. Jobs in the batch execute on one remote host.
        counts: Counter[str] = Counter()

        for job in self:
            local_counts: Counter[str] = Counter()
            for member in job.required_resources():
                rtype, slots = member["type"], int(member["slots"])
                if rtype in ("node", "nodes"):
                    continue
                local_counts[rtype] += slots

            for rtype, count in local_counts.items():
                if count > counts[rtype]:
                    counts[rtype] = count

        counts["cpus"] = max(counts["cpus"], self.cpus)

        group: list[dict[str, Any]] = []
        for rtype, count in counts.items():
            group.extend([{"type": rtype, "slots": 1} for _ in range(count)])
        return group

    def assign_resources(self, allocation: dict[str, Any]) -> None:  # type: ignore[override]
        metadata = allocation.get("metadata", {})

        self.hostname = metadata.get("hostname")
        self.transaction_id = metadata.get("transaction_id")

        if self.hostname is None:
            self.hostname = _single_node_from_allocation(allocation)

        super().assign_resources(allocation)

    def remote_resource_pool(self) -> dict[str, Any]:
        """Return the batch-local topology-aware resource pool.

        The distributed server returns flat per-machine resources. The adapter
        adds ``node`` to checked-out resource specs. For a ResourcePool node's
        own resources, IDs are node-local, so remove the ``node`` field before
        writing the batch-local pool.
        """
        if self.hostname is None:
            self.hostname = _single_node_from_allocation(self.allocation)

        resources = _strip_node_from_resources(self.resources)

        metadata = dict(self.allocation.get("metadata", {}))
        metadata.setdefault("source", "distributed-checkout")
        metadata["hostname"] = self.hostname

        return {
            "allow_multinode": False,
            "additional_properties": metadata,
            "nodes": [
                {
                    "id": self.hostname,
                    "resources": resources,
                }
            ],
        }

    def setup(self) -> None:
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)

        config = {
            "id": self.id,
            "session": self.session,
            "workspace": str(self.workspace.dir),
            "jobs": [job.id for job in self.jobs],
            "status": serialize(self.status),
            "timekeeper": serialize(self.timekeeper),
            "measurements": serialize(self.measurements),
            "local host": os.uname().nodename,
            "remote host": self.hostname,
            "allocation": serialize(self.allocation),
            "resource_pool": self.remote_resource_pool(),
        }

        self.lockfile.write_text(json.dumps(config, indent=2))


def _single_node_from_allocation(allocation: dict[str, Any]) -> str:
    resources = allocation.get("resources", {})

    nodes = {
        str(rspec["node"]) for rspecs in resources.values() for rspec in rspecs if "node" in rspec
    }

    if len(nodes) != 1:
        raise ValueError(f"Expected allocation from one distributed host, got {sorted(nodes)}")

    return next(iter(nodes))


def _strip_node_from_resources(
    resources: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    for rtype, rspecs in resources.items():
        result[rtype] = []

        for rspec in rspecs:
            item = dict(rspec)
            item.pop("node", None)
            result[rtype].append(item)

    return result
