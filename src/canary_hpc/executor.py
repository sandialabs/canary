# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import json
import os
import threading
from typing import Any

import hpc_connect

import canary

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
        config = TestBatch.loadconfig(self.batch)
        self.session: str = config["session"]
        self.cases: list[str] = []
        if case is not None:
            self.cases.append(case)
        else:
            self.cases.extend(config["cases"])
        self.stage = TestBatch.stage(self.batch)
        f = self.stage / "hpc_connect.yaml"
        if not f.exists():
            with open(f, "w") as fh:
                self.backend.config.dump(fh)

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_executor")

    @canary.hookimpl
    def canary_resource_pool_fill(
        self, config: canary.Config, pool: dict[str, dict[str, Any]]
    ) -> None:
        mypool = self.generate_resource_pool()
        f = self.stage / "resource_pool.json"
        if not f.exists():
            f.write_text(json.dumps({"resource_pool": mypool}, indent=2))
        # require full control of resource pool
        pool["additional_properties"].clear()
        pool["additional_properties"].update(mypool["additional_properties"])
        pool["resources"].clear()
        pool["resources"].update(mypool["resources"])

    def run(self, args: argparse.Namespace) -> int:
        n = len(self.cases)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {args.batch_id}")
        workspace = canary.Workspace.load()
        with workspace.session(name=self.session) as session:
            disp = session.run(ids=self.cases)
        canary.config.pluginmanager.hook.canary_runtests_summary(
            cases=disp["cases"], include_pass=False, truncate=10
        )
        return disp["returncode"]

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
            "additional_properties": {"nodes": {"count": node_count}, "backend": self.backend.name},
        }
        return pool
