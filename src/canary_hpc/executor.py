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
    def __init__(self, *, workspace: str, backend: str, job: str | None = None) -> None:
        self.backend: hpc_connect.Backend = hpc_connect.get_backend(backend)
        cfg = TestBatch.loadconfig(workspace)
        self.session: str = cfg["session"]
        self.batch: str = cfg["id"]
        assert workspace == cfg["workspace"]
        self.workspace = Path(cfg["workspace"])
        self.jobs: list[str] = []
        if job is not None:
            self.jobs.append(job)
        else:
            self.jobs.extend(cfg["jobs"])
        if "CANARY_BATCH_ID" not in os.environ:
            os.environ["CANARY_BATCH_ID"] = self.batch
        elif self.batch != os.environ["CANARY_BATCH_ID"]:
            raise ValueError("env batch id inconsistent with cli batch id")

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_executor")

    def run(self, args: argparse.Namespace) -> int:
        n = len(self.jobs)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {self.batch}")
        workspace = canary.Workspace.load()
        f = workspace.logs_dir / f"canary.{self.batch[:7]}.log"
        h = canary.logging.json_file_handler(f)
        canary.logging.add_handler(h)
        specs = workspace.db.load_specs(ids=self.jobs, include_upstreams=True)
        self.modify_specs(specs)
        view_cfg = canary.config.get("workspace:view")
        view_t = canary.ViewSettings(**view_cfg) if view_cfg else canary.ViewSettings.default()
        session = workspace.run(specs, session=self.session, view_t=view_t, only="all")
        return session.returncode

    def load_resource_pool(self) -> dict:
        f = self.workspace / "resource_pool.json"
        fd = json.loads(f.read_text())
        return fd["resource_pool"]

    @canary.hookimpl(tryfirst=True)
    def canary_resource_pool_fill(self, config: canary.Config) -> dict[str, Any] | None:
        """Load the batch-local topology-aware resource pool."""
        return self.load_resource_pool()

    def modify_specs(self, specs: list[canary.JobSpec]) -> None:
        # If a test requests nodes, fill in per-node resources so checkout
        # reserves full nodes. Do not multiply by node_count here; topology-aware
        # checkout applies the resource request independently to each node.
        canonical_name = lambda s: f"{s}s" if not s.endswith("s") else s

        counts: dict[str, int] = {}
        for rtype in self.backend.resource_types():
            name = canonical_name(rtype)
            try:
                counts[name] = self.backend.count_per_node(rtype)
            except ValueError:
                counts[name] = self.backend.count_per_node(name)

        for spec in specs:
            if spec.id not in self.jobs:
                spec.mask = canary.Mask(True, reason=f"Job not in batch {self.batch}")

            params = spec.parameters | spec.meta_parameters
            if params.get("nodes"):
                for rtype, count in counts.items():
                    spec.meta_parameters.setdefault(rtype, count)

    @staticmethod
    def setup_parser(parser: canary.Parser) -> None:
        parser.add_argument(
            "--workers", type=int, help="Run tests in batch using this many workers"
        )
        parser.add_argument(
            "--backend", dest="canary_hpc_backend", help="The HPC connect backend name"
        )
        parser.add_argument("--job", dest="canary_hpc_case", help="Run only this job")
        parser.add_argument(
            "--workspace", dest="canary_hpc_workspace", help="The batch's workspace", required=True
        )
