# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import logging
import os
import sys
import threading
from collections.abc import Mapping
from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any
from typing import Sequence
from typing import TypedDict

import hpc_connect

import canary
from _canary.queue_executor import ResourceQueueExecutor
from _canary.resource_pool import ResourcePool
from _canary.runtest import Runner
from _canary.subcommands.run import Run
from _canary.testexec import ExecutionSpace
from _canary.util import cpu_count
from _canary.util.multiprocessing import SimpleQueue

from .argparsing import CanaryHPCBatchSpec
from .argparsing import CanaryHPCResourceSetter
from .argparsing import CanaryHPCSchedulerArgs
from .batching import BatchingSpec
from .batching import CountTarget
from .batching import allocate_partition_counts
from .batching import batch_jobs
from .batching import normalize_batching_spec
from .batching import partition_jobs
from .batching import set_batch_dependencies
from .batchspec import BatchSpec
from .batchspec import TestBatch
from .queue import ResourceQueue

global_lock = threading.Lock()
logger = canary.get_logger(__name__)


class _BatchRow(TypedDict):
    id: str
    n_jobs: int
    est_s: float
    cheap_s: float | None
    algorithm: str
    node_count: int
    width: str | int


def _log_batch_summary(batch_specs: "list[BatchSpec]") -> None:
    """Log a table summarising the batch pack.

    The table shows one row per batch sorted by descending job count so the
    most loaded batches are immediately visible.
    """
    from rich import box
    from rich.console import Console
    from rich.table import Table

    if not batch_specs:
        return

    # ---- gather per-batch data ----------------------------------------
    rows: list[_BatchRow] = []
    for spec in batch_specs:
        meta = spec.schedule_metadata or {}
        n_jobs = len(spec.jobs)
        est_s = float(spec.estimated_runtime or 0.0)
        algorithm = str(meta.get("algorithm", "unknown"))
        node_count = int(meta.get("node_count", 1))
        width = meta.get("width", "?")
        cheap_raw = meta.get("cheap_runtime")
        cheap_s: float | None = float(cheap_raw) if cheap_raw is not None else None
        rows.append(
            _BatchRow(
                id=spec.id[:7],
                n_jobs=n_jobs,
                est_s=est_s,
                cheap_s=cheap_s,
                algorithm=algorithm,
                node_count=node_count,
                width=width,
            )
        )

    rows.sort(key=lambda r: -r["n_jobs"])

    def _fmt_min(seconds: float) -> str:
        return f"{seconds / 60:.1f} min"

    # ---- emit per-batch debug lines (captured in log file) --------------
    algo_full = rows[0]["algorithm"] if rows else "unknown"
    algo_label = {
        "pack_by_count_simulated": "count/flat",
        "pack_by_count_atomic_simulated": "count/atomic",
        "pack_to_height_simulated": "duration",
    }.get(algo_full, algo_full)
    total_jobs = sum(r["n_jobs"] for r in rows)
    logger.debug(
        "Batch packing summary: algorithm=%s  batches=%d  jobs=%d",
        algo_label,
        len(rows),
        total_jobs,
    )
    for r in rows:
        cheap_note = ""
        if r["cheap_s"] is not None and abs(r["cheap_s"] - r["est_s"]) > 1.0:
            cheap_note = f"  cheap={_fmt_min(r['cheap_s'])}"
        logger.debug(
            "  batch=%s  jobs=%d  nodes=%s  est=%s%s",
            r["id"],
            r["n_jobs"],
            r["node_count"],
            _fmt_min(r["est_s"]),
            cheap_note,
        )

    # ---- build the Rich table (stderr / terminal only) ------------------
    timeout_multiplier: float = 1.0
    try:
        if t := canary.config.get_timeout_option("multiplier"):
            timeout_multiplier = float(t)
    except Exception:
        logger.debug(f"Failed to convert multiplier={t} to float", exc_info=True)

    table = Table(expand=False, box=box.SQUARE)
    table.add_column("Batch", no_wrap=True)
    table.add_column("Jobs", justify="right")
    table.add_column("Nodes", justify="right")
    table.add_column("Width", justify="right")
    table.add_column("Est.", justify="right")
    table.add_column("Alloc", justify="right")

    for r in rows:
        alloc_s: float = r["est_s"] * timeout_multiplier
        # Only annotate with the cheap (pre-simulation) estimate when it differs
        # from the final estimated_runtime — i.e. when exact simulation refined it.
        cheap_s = r["cheap_s"]
        if cheap_s is not None and abs(cheap_s - r["est_s"]) > 1.0:
            cheap_str = f"  [{_fmt_min(cheap_s)} cheap]"
        else:
            cheap_str = ""
        table.add_row(
            r["id"],
            str(r["n_jobs"]),
            str(r["node_count"]),
            str(r["width"]),
            f"{_fmt_min(r['est_s'])}{cheap_str}",
            _fmt_min(alloc_s),
        )

    console = Console(file=sys.stderr)
    console.print(table)


def create_batch_specs(
    *,
    jobs: list["canary.Job"],
    batchspec: BatchingSpec | Mapping[str, Any] | None,
    cpus_per_node: int,
    workers: int | None,
    resources_per_node: dict[str, int] | None = None,
    exact_final_estimate: bool = False,
) -> list[BatchSpec]:
    """Create BatchSpec objects from jobs using the HPC batching policy.

    This helper is intentionally side-effect light so conductor batching can be
    tested without submitting to a backend.
    """
    import dataclasses

    spec = normalize_batching_spec(batchspec)

    partitions = partition_jobs(
        jobs=jobs,
        layout=spec.layout,
        nodes=spec.node_policy,
        cpus_per_node=cpus_per_node,
        resources_per_node=resources_per_node,
    )

    # A positive batch count is only well-defined for a homogeneous set of node
    # counts under layout=flat,nodes=same.  Each distinct node count forms its
    # own partition that is submitted as its own allocation (multi-node jobs run
    # sequentially within their allocation, single-node jobs pack concurrently),
    # so a single global count cannot be honored as a hard limit across a mix of
    # node counts.  Reject it and ask the user to either drop the count (use a
    # duration target) or restrict the selection to a single node count.
    if spec.layout == "flat" and spec.node_policy == "same" and spec.count is not None:
        if not spec.count_is_max():
            node_counts = {partition.node_count for partition in partitions}
            if len(node_counts) > 1:
                raise ValueError(
                    "A batch count (-b count=N) is not supported for layout=flat,nodes=same "
                    f"when jobs span multiple node counts (found {sorted(node_counts)}). "
                    "Use a duration target (-b duration=T) instead, or restrict the "
                    "selection to jobs with a single node count."
                )

    partition_counts = allocate_partition_counts(spec.count, partitions)

    batch_specs: list[BatchSpec] = []

    for partition, partition_count in zip(partitions, partition_counts):
        if partition_count is None:
            partition_spec = spec
        else:
            partition_spec = dataclasses.replace(spec, target=CountTarget(partition_count))

        logger.debug(
            "Batching partition %s: jobs=%d node_count=%d "
            "cpus_per_node=%d width=%d resources=%r count=%r target=%r workers=%r",
            partition.key,
            len(partition.jobs),
            partition.node_count,
            partition.cpus_per_node,
            partition.width,
            partition.resource_capacity,
            partition_count,
            partition_spec.duration,
            workers,
        )

        batch_specs.extend(
            batch_jobs(
                jobs=partition.jobs,
                width=partition.width,
                workers=workers,
                spec=partition_spec,
                resource_capacity=partition.resource_capacity,
                node_count=partition.node_count,
                exact_final_estimate=exact_final_estimate,
            )
        )

    set_batch_dependencies(batch_specs)

    return batch_specs


class CanaryHPCConductor:
    def __init__(self, *, backend: str) -> None:
        hpc_connect.config.export()
        self.backend: hpc_connect.Backend = hpc_connect.get_backend(backend)
        rpool_backend = canary.config.resource_manager.get_property("hpc_backend")
        if rpool_backend != self.backend.name:
            raise ValueError(
                f"expected resource manager backend to be {self.backend.name} but got {rpool_backend}"
            )
        # This private resource pool is only used to schedule local batch
        # submission workers. It is not the HPC test resource pool.
        my_cpus = [{"id": str(j), "slots": 1} for j in range(cpu_count())]
        self.rpool = ResourcePool(
            {
                "additional_properties": {"source": "canary_hpc_conductor"},
                "nodes": [{"id": os.uname().nodename, "resources": {"cpus": my_cpus, "gpus": []}}],
            }
        )

    def register(self, pluginmanager: canary.CanaryPluginManager) -> None:
        pluginmanager.register(self, "canary_hpc_conductor")

    def run(self, args: argparse.Namespace) -> int:
        if getattr(args, "hpc_batch_workers", None) is not None:
            n = int(args.hpc_batch_workers)
            if n > cpu_count():
                logger.warning(f"--hpc-batch-workers={n} > cpu_count={cpu_count()}")
        raw_batchspec = getattr(args, "hpc_batchspec", None)
        batchspec = CanaryHPCBatchSpec.validate_and_set_defaults(raw_batchspec)
        args.hpc_batchspec = batchspec
        setattr(canary.config.options, "hpc_batchspec", batchspec)
        console_style = canary.config.getoption("console_style") or {}
        if "live_columns" not in console_style:
            console_style["live_columns"] = "Job,ID,Status,Queued,Running,Elapsed,Rank"
        setattr(canary.config.options, "console_style", console_style)
        return Run().execute(args)

    def backend_count_per_node(self, rtype: str) -> int:
        """Return homogeneous backend resource count per node.

        Tries both plural and singular resource type spellings.
        """
        candidates = [rtype]

        if rtype.endswith("s"):
            candidates.append(rtype[:-1])
        else:
            candidates.append(f"{rtype}s")

        errors: list[str] = []

        for candidate in candidates:
            try:
                count = int(self.backend.count_per_node(candidate))
            except Exception as e:
                errors.append(f"{candidate}: {e}")
                continue

            if count <= 0:
                raise ValueError(
                    f"Backend {self.backend.name!r} reports non-positive "
                    f"{candidate}_per_node={count}"
                )

            return count

        details = "; ".join(errors)
        raise ValueError(
            f"Could not determine {rtype!r} count per node for backend "
            f"{self.backend.name!r}: {details}"
        )

    def backend_resources_per_node(self) -> dict[str, int]:
        """Return homogeneous resource capacities per backend node.

        CPU capacity is required.  Other resource types are included when they
        are available and homogeneous across backend nodes.
        """
        resources: dict[str, int] = {}

        resources["cpus"] = self.backend_count_per_node("cpus")

        # Prefer resource-manager types because they include plugin-provided
        # resources known to Canary.
        rtypes: set[str] = set()
        try:
            rtypes.update(canary.config.resource_manager.types())
        except Exception:
            logger.debug("Could not query Canary resource manager types", exc_info=True)

        # Ensure common resource types are considered.
        rtypes.update({"cpus", "gpus"})

        for rtype in sorted(rtypes):
            if rtype in ("cpu", "cpus"):
                continue

            try:
                count = self.backend_count_per_node(rtype)
            except Exception:
                logger.debug("Skipping backend resource type %r", rtype, exc_info=True)
                continue

            if count > 0:
                resources[rtype] = int(count)

        return resources

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: "Runner") -> bool:
        """Run each job in ``runner.jobs``.

        Args:
        job: job to run

        Returns:
        The session returncode (0 for success)

        """
        batchspec = canary.config.getoption("hpc_batchspec")
        if not batchspec:
            raise ValueError("Cannot partition jobs: missing batching options")

        workers = canary.config.getoption("hpc_batch_workers")
        if workers is not None:
            workers = int(workers)

        logger.info(
            "[bold]Batching[/] %d jobs for submission to the [bold]%s[/] backend",
            len(runner.jobs),
            self.backend.name,
        )
        resources_per_node = self.backend_resources_per_node()
        cpus_per_node = resources_per_node["cpus"]

        batch_specs = create_batch_specs(
            jobs=runner.jobs,
            batchspec=batchspec,
            cpus_per_node=cpus_per_node,
            workers=workers,
            resources_per_node=resources_per_node,
            exact_final_estimate=bool(canary.config.getoption("hpc_batch_exact_estimate")),
        )

        if not batch_specs:
            raise ValueError(
                "No test batches generated (this should never happen, "
                "the default batching scheme should have been used)"
            )
        if missing := {c.id for c in runner.jobs} - {c.id for b in batch_specs for c in b.jobs}:
            raise ValueError(f"Jobs missing from batches: {', '.join(missing)}")
        key = canary.string.pluralize("batch", n=len(batch_specs))
        fmt = "[bold]Generated[/] %d batches %s from %d jobs"
        logger.info(fmt, len(batch_specs), key, len(runner.jobs))
        _log_batch_summary(batch_specs)
        root = runner.workspace.sessions_dir / runner.session / "batches"
        logger.debug("Batch workspace root: %s", root)
        graph: dict[str, list[str]] = {}
        specmap: dict[str, BatchSpec] = {}
        for batch_spec in batch_specs:
            graph[batch_spec.id] = [d.id for d in batch_spec.dependencies]
            specmap[batch_spec.id] = batch_spec
        batches: dict[str, TestBatch] = {}
        ts = TopologicalSorter(graph)
        for id in ts.static_order():
            batch_spec = specmap[id]
            path = batch_spec.id[:7]
            workspace = ExecutionSpace(root=root, path=Path(path), session=runner.session)
            dependencies = [batches[dep.id] for dep in batch_spec.dependencies]
            batch = TestBatch(
                batch_spec,
                workspace=workspace,
                dependencies=dependencies,
                backend_supports_dependencies=self.backend.supports_dependencies(),
            )
            logger.debug(
                "Created batch workspace: %s  jobs=%d  deps=%d",
                workspace.dir,
                len(batch_spec.jobs),
                len(dependencies),
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
            dest="hpc_backend",
            default=os.getenv("CANARY_HPC_BACKEND") or argparse.SUPPRESS,
            metavar="BACKEND",
            help="Submit batches to this HPC scheduler [alias: -b backend=BACKEND] [default: None]",
        )
        parser.add_argument(
            "--submit-arg",
            "--scheduler-args",
            dest="hpc_submit_args",
            metavar="ARGS",
            action=CanaryHPCSchedulerArgs,
            help="Comma separated list of options to pass directly "
            "to the scheduler [alias: -b options=ARGS]",
        )
        parser.add_argument(
            "--batch-spec",
            dest="hpc_batchspec",
            metavar="SPEC",
            action=CanaryHPCBatchSpec,
            help="Comma separated list of options to partition jobs into batches. "
            "See canary batch help --spec for help on batch specification syntax "
            "[alias: -b spec=SPEC]",
        )
        parser.add_argument(
            "--batch-workers",
            dest="hpc_batch_workers",
            metavar="WORKERS",
            type=int,
            help="Run jobs in batches using WORKERS workers [alias: -b workers=WORKERS]",
        )
        parser.add_argument(
            "--batch-timeout-strategy",
            dest="hpc_batch_timeout_strategy",
            metavar="STRATEGY",
            choices=("aggressive", "conservative"),
            help="Estimate batch runtime (queue time) conservatively or aggressively "
            "[alias: -b timeout=STRATEGY] [default: aggressive]",
        )
        parser.add_argument(
            "--batch-exact-estimate",
            dest="hpc_batch_exact_estimate",
            action="store_true",
            default=False,
            help=(
                "After forming batches with cheap schedule estimates, run an exact "
                "scalar scheduler simulation once per final batch to refine the "
                "stored runtime estimate.  This is slower for very large suites."
            ),
        )

    @staticmethod
    def setup_legacy_parser(parser: canary.Parser) -> None:
        p = LegacyParserAdapter(parser)
        CanaryHPCConductor.setup_parser(p)


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


def standalone_resource_pool() -> ResourcePool:
    """Create standalone resource pool, only used to schedule local batch
    submission workers. It is not the HPC test resource pool.
    """
    my_cpus = [{"id": str(j), "slots": 1} for j in range(cpu_count())]
    rpool = ResourcePool(
        {
            "additional_properties": {"source": "canary_hpc_conductor"},
            "nodes": [{"id": os.uname().nodename, "resources": {"cpus": my_cpus, "gpus": []}}],
        }
    )
    return rpool


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
