# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import json
import os
import threading
from typing import Any
from typing import Sequence

import hpc_connect

import canary
from _canary.plugins.builtin.executor import Runner
from _canary.plugins.types import Result
from _canary.queue import ResourceQueue
from _canary.queue import process_queue
from _canary.resource_pool import ResourcePool

from .batching import TestBatch

global_lock = threading.Lock()
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
        pool = self.generate_resource_pool()
        self.pool = ResourcePool(pool)
        stage = TestBatch.stage(self.batch)
        f = os.path.join(stage, "resource_pool.json")
        if not os.path.exists(f):
            with open(f, "w") as fh:
                json.dump({"resource_pool": pool}, fh, indent=2)
        stage = TestBatch.stage(self.batch)
        f = os.path.join(stage, "hpc_connect.yaml")
        if not os.path.exists(f):
            with open(f, "w") as fh:
                self.backend.config.dump(fh)

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_executor")

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

    def run(self, args: argparse.Namespace) -> int:
        n = len(self.cases)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {args.batch_id}")
        case_specs = [f"/{case}" for case in self.cases]
        session = canary.Session.casespecs_view(os.getcwd(), case_specs)
        session.run()
        canary.config.pluginmanager.hook.canary_runtests_summary(
            cases=session.active_cases(), include_pass=False, truncate=10
        )
        return session.exitstatus

    @canary.hookimpl
    def canary_resource_count(self, type: str) -> int:
        node_count = self.backend.config.node_count
        if type in ("nodes", "node"):
            return node_count
        type_per_node = self.backend.config.count_per_node(type)
        return node_count * type_per_node

    @canary.hookimpl
    def canary_resources_avail(self, case: canary.TestCase) -> Result:
        return self.pool.accommodates(case.required_resources())

    @canary.hookimpl
    def canary_resource_types(self) -> list[str]:
        return self.pool.types

    @canary.hookimpl
    def canary_runtests(self, cases: Sequence["canary.TestCase"]) -> int:
        """Run each test case in ``cases``.

        Args:
        cases: test cases to run

        Returns:
        The session returncode (0 for success)

        """
        queue = ResourceQueue.factory(global_lock, cases, resource_pool=self.pool)
        runner = Runner()
        return process_queue(queue, runner)

    @staticmethod
    def setup_parser(parser: canary.Parser) -> None:
        parser.add_argument(
            "--workers", type=int, help="Run tests in batch using this many workers"
        )
        parser.add_argument(
            "--backend", dest="canary_hpc_backend", help="The HPC connect backend name"
        )
        parser.add_argument("--case", dest="canary_hpc_case", help="Run only this case")
        parser.add_argument("batch_id")
