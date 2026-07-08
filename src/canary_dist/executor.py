# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import threading
from pathlib import Path

import canary

from .batchspec import TestBatch

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


class DistributedPoolExecutor:
    def __init__(self, workspace: str, job: str | None = None) -> None:
        src = canary.config.resource_manager.get_property("source")
        if src != "distributed-checkout":
            raise ValueError(
                f"expected resource manager source to be 'distributed-checkout' but got {src}"
            )
        self.config = TestBatch.loadconfig(workspace)
        self.session: str = self.config["session"]
        self.batch: str = self.config["id"]
        assert workspace == self.config["workspace"]
        self.workspace = Path(self.config["workspace"])
        self.jobs: list[str] = []
        if job is not None:
            self.jobs.append(job)
        else:
            self.jobs.extend(self.config["jobs"])
        if "CANARY_BATCH_ID" not in os.environ:
            os.environ["CANARY_BATCH_ID"] = self.batch
        elif self.batch != os.environ["CANARY_BATCH_ID"]:
            raise ValueError("env batch id inconsistent with cli batch id")

    def run(self, args: argparse.Namespace) -> int:
        n = len(self.jobs)
        workspace = canary.Workspace.load()
        f = workspace.logs_dir / f"canary.{self.batch[:7]}.log"
        h = canary.logging.json_file_handler(f)
        canary.logging.add_handler(h)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {self.batch}")
        specs = workspace.db.load_specs(ids=self.jobs, include_upstreams=True)
        for spec in specs:
            if spec.id not in self.jobs:
                spec.mask = canary.Mask(True, reason=f"Job not in batch {self.batch}")
        view_cfg = canary.config.get("workspace:view")
        view_t = canary.ViewSettings(**view_cfg) if view_cfg else canary.ViewSettings.default()
        session = workspace.run(specs, session=self.session, view_t=view_t, only="all")
        return session.returncode

    @staticmethod
    def setup_parser(parser: canary.Parser) -> None:
        parser.add_argument(
            "--workers", type=int, help="Run tests in batch using this many workers"
        )
        parser.add_argument(
            "--workspace", dest="dist_workspace", help="The batch's workspace", required=True
        )
