# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import json
import os
import threading
from pathlib import Path
from typing import Any

import hpc_connect

import canary

from .batchspec import TestBatch

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


class CanaryHPCExecutor:
    def __init__(self, *, workspace: str, backend: str, case: str | None = None) -> None:
        self.backend: hpc_connect.HPCSubmissionManager = hpc_connect.get_backend(backend)
        config = TestBatch.loadconfig(workspace)
        self.session: str = config["session"]
        self.batch: str = config["id"]
        assert workspace == config["workspace"]
        self.workspace = Path(config["workspace"])
        self.cases: list[str] = []
        if case is not None:
            self.cases.append(case)
        else:
            self.cases.extend(config["cases"])
        f = self.workspace / "hpc_connect.yaml"
        if not f.exists():
            with open(f, "w") as fh:
                self.backend.config.dump(fh)
        if "CANARY_BATCH_ID" not in os.environ:
            os.environ["CANARY_BATCH_ID"] = self.batch
        elif self.batch != os.environ["CANARY_BATCH_ID"]:
            raise ValueError("env batch id inconsistent with cli batch id")

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_executor")

    def run(self, args: argparse.Namespace) -> int:
        n = len(self.cases)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {self.batch}")
        workspace = canary.Workspace.load()
        specs = workspace.load_testspecs(ids=self.cases)
        session = workspace.run(specs, session_name=self.session, update_view=False, only="all")
        return session.returncode

    @canary.hookimpl
    def canary_resource_pool_fill(
        self, config: canary.Config, pool: dict[str, dict[str, Any]]
    ) -> None:
        mypool = self.generate_resource_pool()
        f = self.workspace / "resource_pool.json"
        if not f.exists():
            f.write_text(json.dumps({"resource_pool": mypool}, indent=2))
        # require full control of resource pool
        pool["additional_properties"].clear()
        pool["additional_properties"].update(mypool["additional_properties"])
        pool["resources"].clear()
        pool["resources"].update(mypool["resources"])

    @staticmethod
    def setup_parser(parser: canary.Parser) -> None:
        parser.add_argument(
            "--workers", type=int, help="Run tests in batch using this many workers"
        )
        parser.add_argument(
            "--backend", dest="canary_hpc_backend", help="The HPC connect backend name"
        )
        parser.add_argument("--case", dest="canary_hpc_case", help="Run only this case")
        parser.add_argument(
            "--workspace", dest="canary_hpc_workspace", help="The batch's workspace", required=True
        )

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
