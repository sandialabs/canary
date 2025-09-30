# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
from typing import Any

import hpc_connect

import canary

from .testbatch import TestBatch

logger = canary.get_logger(__name__)


class BatchExecutor:
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
        config.options.mode = "a"
        case_specs = self.case_specs
        n = len(case_specs)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {self.batch}")
        setattr(config.options, "case_specs", case_specs)

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
            "additional_properties": {"nodes": node_count},
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
    def canary_resource_satisfiable(self, case: canary.TestCase) -> bool:
        # The resource pool was already set above, so we can just leverage it
        return canary.config.resource_pool.satisfiable(case.required_resources())

    @canary.hookimpl
    def canary_resource_types(self) -> list[str]:
        # The resource pool was already set above, so we can just leverage it
        return canary.config.resource_pool.types
