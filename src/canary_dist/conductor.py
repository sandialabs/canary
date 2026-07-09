# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import logging
import os
import threading
from pathlib import Path
from typing import Any

import hpc_connect

import canary
from _canary.plugins.subcommands.run import Run
from _canary.queue_executor import ResourceQueueExecutor
from _canary.runtest import Runner
from _canary.testexec import ExecutionSpace
from _canary.util.multiprocessing import SimpleQueue
from canary_hpc.batching import batch_jobs
from canary_hpc.batchspec import BatchSpec

from .adapter import DistributedResourcePoolAdapter
from .batchspec import TestBatch
from .queue import ResourceQueue

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


class DistributedPoolConductor:
    def __init__(self, *, server_url: str) -> None:
        logger.debug(f"Connecting to distributed pool at {server_url}")
        hpc_connect.config.export()
        self.backend: hpc_connect.Backend = hpc_connect.get_backend("remote_subprocess")
        self.dpool = DistributedResourcePoolAdapter(server_url=server_url)
        src = canary.config.resource_manager.get_property("source")
        if src != "canary-dist":
            raise ValueError(
                f"expected resource manager backend to be 'canary-dist' but got {src!r}"
            )

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_dist_conductor")

    def run(self, args: argparse.Namespace) -> int:
        return Run().execute(args)

    def pool_state(self) -> dict[str, Any]:
        """determine if the resources for this test are available"""
        return self.dpool.current_state()

    @canary.hookimpl
    def canary_select_modifyitems(self, selector: canary.Selector) -> None:
        width = canary.config.getoption("dist_batch_width") or 8
        for spec in selector.specs:
            parameters = spec.parameters | spec.meta_parameters
            if parameters.get("cpus", 1) > width:
                spec.mask = canary.Mask.masked("Required number of CPUs exceeds batch width")

    @canary.hookimpl
    def canary_runtests_start(self, runner: Runner) -> None:
        logger.info(f"Connected to distributed pool at {self.dpool.server_url}")

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: Runner) -> bool:
        """Run each test job in ``jobs``.

        Returns:
        The session returncode (0 for success)

        """
        width = canary.config.getoption("dist_batch_width") or 8
        batch_specs: list[BatchSpec] = batch_jobs(
            jobs=runner.jobs,
            duration=canary.config.getoption("dist_batch_duration"),
            width=width,
            count=canary.config.getoption("dist_batch_count"),
            layout="flat",
            nodes="any",
        )
        if not batch_specs:
            raise ValueError("No test batches generated")
        fmt = "[bold]Generated[/] %d batches from %d jobs"
        logger.info(fmt % (len(batch_specs), len(runner.jobs)))
        root = runner.workspace.cache_dir / "canary-dist"
        batches: list[TestBatch] = []
        for batch_spec in batch_specs:
            path = f"batches/{batch_spec.id[:7]}"
            workspace = ExecutionSpace(root=root, path=Path(path), session=runner.session)
            batch = TestBatch(batch_spec, workspace=workspace)
            if width > batch.cpus:
                batch.cpus = width
            batches.append(batch)
        try:
            queue = ResourceQueue(global_lock, resource_pool=self.dpool)  # type: ignore
            queue.put(*batches)  # type: ignore
            queue.prepare()
        except:
            logger.exception("failed")
            raise
        executor = DistExecutor()
        max_workers = canary.config.getoption("workers") or -1
        with ResourceQueueExecutor(queue, executor, max_workers=max_workers) as ex:
            ex.run(backend=self.backend.name)
        return True

    @staticmethod
    def add_server_argument(parser: canary.Parser | argparse._ArgumentGroup) -> None:
        parser.add_argument(
            "--server-url",
            dest="dist_server_url",
            metavar="URL",
            default=os.getenv("CANARY_DIST_SERVER_URL") or argparse.SUPPRESS,
            help="Distributed pool server location (URL). "
            "Defaults to CANARY_DIST_SERVER_URL environment variable, if defined.",
        )

    @staticmethod
    def setup_parser(parser: canary.Parser) -> None:
        Run().setup_parser(parser)
        parser.description = (
            "Batch jobs and run batches remotely across a distributed pool of machines."
        )
        group = "distributed pool execution"
        group = super(canary.Parser, parser).add_argument_group(group)
        DistributedPoolConductor.add_server_argument(group)
        group.add_argument(
            "--tags",
            dest="dist_tags",
            metavar="TAGS",
            type=lambda arg: [_.strip() for _ in arg.split(",") if _.strip()],
            help="Only run on machines matching all tags (comma separated list of tags)",
        )
        group.add_argument(
            "--batch-width",
            dest="dist_batch_width",
            metavar="N",
            default=8,
            type=int,
            help="Width of job batches (in CPUs) [default: %(default)s]",
        )
        group.add_argument(
            "--batch-count",
            dest="dist_batch_count",
            metavar="N",
            default=None,
            type=int,
            help="Number of job batches [default: auto]",
        )
        group.add_argument(
            "--batch-duration",
            dest="dist_batch_duration",
            default=None,
            metavar="T",
            type=canary.time.time_in_seconds,
            help="Approximate test batch duration in seconds [default: 10m]",
        )
        group.add_argument(
            "-E",
            "--export",
            metavar="<variables>|ALL",
            dest="dist_export",
            type=export_splitter,
            help="Identify which environment variables from the submission environment are "
            "propagated to the remote host.  By default, no variables are propagated.\n\n"
            "--export=ALL: All environment variables will be propagated.\n\n"
            "--export=<variables>: Comma separated list of variables to propagate. "
            "Environment variable names may be specified to propagate the current value "
            "(e.g. '--export=SPAM') or specific values may be exported "
            "(e.g. '--export=SPAM=eggs').  If the variable LOADEDMODULES is exported, the "
            "the modules will be explicitly loaded on the remote host.",
        )

    @staticmethod
    def validate_and_set_defaults(args: argparse.Namespace) -> None:
        server = getattr(args, "dist_server_url", None)
        if server is None:
            raise ValueError(
                "canary dist: missing required argument --server-url or CANARY_DIST_SERVER_URL"
            )


def export_splitter(arg: str) -> dict[str, Any]:
    export: dict[str, str] = {}
    items = [_.strip() for _ in arg.split(",") if _.split()]
    for item in items:
        if item == "ALL":
            export.clear()
            export["ALL"] = "==YES=="
            break
        if "=" in item:
            var, _, value = item.partition("=")
            export[var] = value
        else:
            export[item] = "==YES=="
    return export


class DistExecutor:
    """Class for running ``AbstractJob``."""

    def __call__(self, batch: TestBatch, queue: SimpleQueue, **kwargs: Any) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        canary.config.ensure_loaded()
        hpc = logging.getLogger("hpc_connect")
        hpc.handlers.clear()
        hpc.propagate = True
        hpc.setLevel(logging.NOTSET)
        backend_name = kwargs["backend"]
        assert backend_name == "remote_subprocess"
        backend = hpc_connect.get_backend(backend_name)
        batch.setup()
        batch.run(backend=backend, queue=queue)
