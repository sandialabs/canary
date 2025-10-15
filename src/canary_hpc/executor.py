# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from typing import Any

import hpc_connect

import canary
from _canary.plugins.types import Result

from .testbatch import TestBatch

logger = canary.get_logger(__name__)


class CanaryHPCExecutor:
    def __init__(self, *, backend: str, batch: str, case: str | None = None) -> None:
        self.backend: hpc_connect.HPCSubmissionManager = hpc_connect.get_backend(backend)
        if "CANARY_BATCH_ID" not in os.environ:
            os.environ["CANARY_BATCH_ID"] = batch
        elif batch != os.environ["CANARY_BATCH_ID"]:
            raise ValueError("env batch id inconsistent with cli batch id")
        self.batch = batch
        self.cases: list[str] = []
        if case is not None:
            self.cases.append(case)
        else:
            cases = TestBatch.loadindex(self.batch)
            self.cases.extend(cases)

    def setup(self, *, config: canary.Config) -> None:
        pool = self.generate_resource_pool()
        config.resource_pool.fill(pool)
        stage = TestBatch.stage(self.batch)
        f = os.path.join(stage, "resource_pool.json")
        if not os.path.exists(f):
            with open(f, "w") as fh:
                json.dump({"resource_pool": pool}, fh, indent=2)
        f = os.path.join(stage, "hpc_connect.yaml")
        if not os.path.exists(f):
            with open(f, "w") as fh:
                self.backend.config.dump(fh)

    def generate_resource_pool(self) -> dict[str, Any]:
        # set the resource pool for this backend
        resources: dict[str, list[Any]] = {}
        node_count = self.backend.config.node_count
        for type in self.backend.config.resource_types():
            if not type.endswith("s"):
                type += "s"
            count = self.backend.config.count_per_node(type)
            slots = 1
            resources[type] = [{"id": str(j), "slots": slots} for j in range(count * node_count)]
        pool: dict[str, Any] = {
            "resources": resources,
            "additional_properties": {"nodes": node_count, "backend": self.backend.name},
        }
        return pool

    @property
    def case_specs(self) -> list[str]:
        return [f"/{case}" for case in self.cases]

    @canary.hookimpl
    def canary_resource_count(self, type: str) -> int:
        node_count = self.backend.config.node_count
        if type in ("nodes", "node"):
            return node_count
        type_per_node = self.backend.config.count_per_node(type)
        return node_count * type_per_node

    @canary.hookimpl
    def canary_resources_avail(self, case: canary.TestCase) -> Result:
        # The resource pool was already set above, so we can just leverage it
        return canary.config.resource_pool.accommodates(case)

    @canary.hookimpl
    def canary_resource_types(self) -> list[str]:
        # The resource pool was already set above, so we can just leverage it
        return canary.config.resource_pool.types
