# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import logging
import os
import threading
from collections import Counter
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any
from typing import Sequence

import hpc_connect

import canary
from _canary.plugins.subcommands.run import Run
from _canary.queue_executor import ResourceQueueExecutor
from _canary.resource_pool import ResourcePool
from _canary.runtest import Runner
from _canary.testexec import ExecutionSpace
from _canary.util import cpu_count
from _canary.util.multiprocessing import SimpleQueue
from _canary.util.time import time_in_seconds

from .argparsing import CanaryHPCBatchSpec
from .argparsing import CanaryHPCResourceSetter
from .argparsing import CanaryHPCSchedulerArgs
from .batching import batch_jobs
from .batchspec import BatchSpec
from .batchspec import TestBatch
from .queue import ResourceQueue

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


class CanaryHPCConductor:
    def __init__(self, *, backend: str) -> None:
        hpc_connect.config.export()
        self.backend: hpc_connect.Backend = hpc_connect.get_backend(backend)

        # Compute available resource types reported by hpc-connect.
        self._slots_per_resource_type: Counter[str] | None = None
        rtypes: set[str] = {"cpus", "gpus"}
        for rtype in self.backend.resource_types():
            rtype = rtype if rtype.endswith("s") else f"{rtype}s"
            rtypes.add(rtype)
        self.available_resource_types = sorted(rtypes)

        # This private resource pool is only used to schedule local batch
        # submission workers. It is not the HPC test resource pool.
        self.rpool = ResourcePool(
            {
                "additional_properties": {"source": "canary_hpc_batch_conductor"},
                "nodes": [
                    {
                        "id": os.uname().nodename,
                        "resources": {
                            "cpus": [{"id": str(j), "slots": 1} for j in range(cpu_count())],
                            "gpus": [],
                        },
                    }
                ],
            }
        )

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_conductor")

    def run(self, args: argparse.Namespace) -> int:
        if n := args.canary_hpc_batch_workers:
            if n > cpu_count():
                logger.warning(f"--hpc-batch-workers={n} > cpu_count={cpu_count()}")
        batchspec = args.canary_hpc_batchspec or CanaryHPCBatchSpec.defaults()
        CanaryHPCBatchSpec.validate_and_set_defaults(batchspec)
        setattr(canary.config.options, "canary_hpc_batchspec", batchspec)
        console_style = canary.config.getoption("console_style") or {}
        if "live_columns" not in console_style:
            console_style["live_columns"] = "Job,ID,Status,Queued,Elapsed,Rank"
        setattr(canary.config.options, "console_style", console_style)
        return Run().execute(args)

    @canary.hookimpl(tryfirst=True)
    def canary_resource_pool_fill(self, config: canary.Config) -> dict[str, Any] | None:
        """Create a topology-aware resource pool representing the HPC backend.

        Node IDs are virtual/backend-local bookkeeping IDs. Canary core does not
        need to know where the scheduler will physically place the job.
        """
        node_count = self.backend.node_count

        resource_types = {
            _canonical_resource_type(rtype) for rtype in self.backend.resource_types()
        }
        resource_types.update({"cpus", "gpus"})

        nodes: list[dict[str, Any]] = []

        for i in range(node_count):
            resources: dict[str, list[dict[str, Any]]] = {}

            for rtype in sorted(resource_types):
                try:
                    count = self.backend.count_per_node(rtype)
                except ValueError:
                    try:
                        count = self.backend.count_per_node(_singular_resource_type(rtype))
                    except ValueError:
                        count = 0

                resources[rtype] = _resource_specs(count, rtype=rtype)

            nodes.append(
                {
                    "id": str(i),
                    "resources": resources,
                }
            )

        return {
            "allow_multi_node": True,
            "additional_properties": {
                "backend": self.backend.name,
                "source": "hpc",
                "node_count": node_count,
            },
            "nodes": nodes,
        }

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: "Runner") -> bool:
        """Run each job in ``runner.jobs``.

        Args:
        job: job to run

        Returns:
        The session returncode (0 for success)

        """
        batchspec = canary.config.getoption("canary_hpc_batchspec")
        if not batchspec:
            raise ValueError("Cannot partition jobs: missing batching options")
        batch_specs: list[BatchSpec] = batch_jobs(
            jobs=runner.jobs,
            layout=batchspec["layout"],
            count=batchspec["count"],
            duration=batchspec["duration"],
            nodes=batchspec["nodes"],
        )
        if not batch_specs:
            raise ValueError(
                "No test batches generated (this should never happen, "
                "the default batching scheme should have been used)"
            )
        if missing := {c.id for c in runner.jobs} - {c.id for b in batch_specs for c in b.jobs}:
            raise ValueError(f"Jobs missing from batches: {', '.join(missing)}")
        key = canary.string.pluralize("batch", n=len(batch_specs))
        fmt = "[bold]Generated[/] %d test %s from %d jobs"
        logger.info(fmt % (len(batch_specs), key, len(runner.jobs)))
        root = runner.workspace.cache_dir / "canary-hpc"
        graph: dict[str, list[str]] = {}
        specmap: dict[str, BatchSpec] = {}
        for batch_spec in batch_specs:
            graph[batch_spec.id] = [d.id for d in batch_spec.dependencies]
            specmap[batch_spec.id] = batch_spec
        batches: dict[str, TestBatch] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            batch_spec = specmap[id]
            path = f"batches/{batch_spec.id[:7]}"
            workspace = ExecutionSpace(root=root, path=Path(path), session=runner.session)
            dependencies = [batches[dep.id] for dep in batch_spec.dependencies]
            batch = TestBatch(
                batch_spec,
                workspace=workspace,
                dependencies=dependencies,
                backend_supports_dependencies=self.backend.supports_dependencies(),
            )
            batches[batch.id] = batch
        queue = ResourceQueue(global_lock, resource_pool=self.rpool)
        queue.put(*batches.values())  # type: ignore
        queue.prepare()
        executor = BatchExecutor()
        max_workers = canary.config.getoption("workers") or 10
        with ResourceQueueExecutor(queue, executor, max_workers=max_workers) as ex:
            ex.run(backend=self.backend.name)

        return True

    @staticmethod
    def setup_parser(
        parser: "canary.Parser | LegacyParserAdapter | argparse._ArgumentGroup",
    ) -> None:
        """Exists to accomodate ``canary hpc run`` and ``canary run -b ...``"""
        parser.add_argument(
            "--backend",
            "--scheduler",
            dest="canary_hpc_backend",
            metavar="BACKEND",
            help="Submit batches to this HPC scheduler [alias: -b backend=BACKEND] [default: None]",
        )
        parser.add_argument(
            "--scheduler-args",
            dest="canary_hpc_scheduler_args",
            metavar="ARGS",
            action=CanaryHPCSchedulerArgs,
            help="Comma separated list of options to pass directly "
            "to the scheduler [alias: -b options=ARGS]",
        )
        parser.add_argument(
            "--batch-spec",
            dest="canary_hpc_batchspec",
            metavar="SPEC",
            action=CanaryHPCBatchSpec,
            help="Comma separated list of options to partition jobs into batches. "
            "See canary batch help --spec for help on batch specification syntax "
            "[alias: -b spec=SPEC]",
        )
        parser.add_argument(
            "--batch-workers",
            dest="canary_hpc_batch_workers",
            metavar="WORKERS",
            help="Run jobs in batches using WORKERS workers [alias: -b workers=WORKERS]",
        )
        parser.add_argument(
            "--batch-timeout-strategy",
            dest="canary_hpc_batch_timeout_strategy",
            metavar="STRATEGY",
            choices=("aggressive", "conservative"),
            help="Estimate batch runtime (queue time) conservatively or aggressively "
            "[alias: -b timeout=STRATEGY] [default: aggressive]",
        )
        parser.add_argument(
            "--queue-timeout",
            dest="canary_hpc_queue_timeout",
            metavar="T",
            type=time_in_seconds,
            default=30 * 60,
            help="Maximum time to wait in queue [alias: -b queue_timeout=T] [default: 30min]",
        )

    @staticmethod
    def setup_legacy_parser(parser: canary.Parser) -> None:
        p = LegacyParserAdapter(parser)
        CanaryHPCConductor.setup_parser(p)


def _canonical_resource_type(rtype: str) -> str:
    return rtype if rtype.endswith("s") else f"{rtype}s"


def _singular_resource_type(rtype: str) -> str:
    return rtype[:-1] if rtype.endswith("s") else rtype


def _resource_specs(count: int, *, rtype: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    for j in range(count):
        spec: dict[str, Any] = {
            "id": str(j),
            "slots": 1,
        }

        if rtype == "gpus":
            spec["properties"] = {"vendor": "UNKNOWN"}

        specs.append(spec)

    return specs


class LegacyParserAdapter:
    def __init__(self, parser: "canary.Parser") -> None:
        self.parser = parser
        self.parser.add_argument(
            "-b",
            command="run",
            group="canary hpc",
            metavar="option=value",
            action=CanaryHPCResourceSetter,
            help="Short cut for setting batch options.",
        )

    def add_argument(self, flag: str, *args, **kwargs):
        flag = "--hpc-" + flag[2:]
        self.parser.add_argument(flag, *args, command="run", group="canary hpc", **kwargs)

    def parse_args(self, args: Sequence[str] | None = None) -> argparse.Namespace:
        return self.parser.parse_args(args)


class KeyboardQuit(Exception):
    pass


class BatchExecutor:
    """Class for running ``ResourceQueue``."""

    def __call__(self, batch: TestBatch, queue: SimpleQueue, **kwargs: Any) -> None:
        # Ensure the config is loaded, since this may be called in a new subprocess
        hpc = logging.getLogger("hpc_connect")
        hpc.handlers.clear()
        hpc.propagate = True
        hpc.setLevel(logging.NOTSET)
        batch.setup()
        backend: hpc_connect.Backend = hpc_connect.get_backend(kwargs["backend"])
        batch.run(backend=backend, queue=queue)
        logger.debug(f"Done running {batch}")
