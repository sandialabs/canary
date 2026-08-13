# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING
from typing import Any

import canary
from _canary.hookspec import hookimpl
from _canary.util.time import time_in_seconds

if TYPE_CHECKING:
    from _canary.config.argparsing import Parser
    from _canary.config.config import Config as CanaryConfig
    from _canary.runtest import Runner


logger = canary.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Flux())


class Flux(canary.CanarySubcommand):
    name = "flux"
    description = "Run Canary tests through Flux"

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="flux_command", required=True)

        p = subparsers.add_parser(
            "run",
            help="Run Canary jobs individually inside a Flux allocation",
            description="Run Canary jobs individually inside a Flux allocation",
        )
        FluxRun.setup_parser(p)

        p = subparsers.add_parser(
            "exec",
            help="Execute one Canary job inside a Flux allocation",
            description="Execute one Canary job inside a Flux allocation",
        )
        FluxExec.setup_parser(p)

    def execute(self, args: argparse.Namespace) -> int:
        if args.flux_command == "run":
            return FluxRun().execute(args)
        if args.flux_command == "exec":
            return FluxExec().execute(args)
        raise ValueError(f"canary flux: unknown subcommand {args.flux_command!r}")


class FluxRun:
    """
    Implements:

        canary flux run ...

    """

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        parser.set_defaults(flux_direct_run=True)
        group = parser.add_argument_group("flux options")
        group.add_argument(
            "--nodes",
            dest="flux_nodes",
            type=int,
            default=None,
            metavar="N",
            help="Minimum number of nodes to request for the Flux allocation [default: auto]",
        )
        group.add_argument(
            "--queue-timeout",
            dest="flux_queue_timeout",
            type=time_in_seconds,
            default=1200,
            metavar="T",
            help="Maximum time to wait for the Flux allocation to start [default: 1200s]",
        )
        group.add_argument(
            "--time-limit",
            dest="flux_time_limit",
            type=time_in_seconds,
            default=3600,
            metavar="T",
            help="Flux allocation time limit [default: 3600s]",
        )
        group.add_argument(
            "--max-submitted",
            dest="flux_max_submitted",
            type=int,
            default=0,
            metavar="N",
            help="Maximum number of simultaneously submitted inner Flux jobs; 0 means unlimited",
        )

        group.add_argument(
            "--submit-arg",
            dest="flux_submit_args",
            action="append",
            default=None,
            metavar="ARG",
            help="Additional argument passed to inner Flux/hpc_connect job submission; may be repeated",
        )

        from _canary.plugins.subcommands.run import Run

        Run().setup_parser(parser)

    def execute(self, args: argparse.Namespace) -> int:
        from _canary.plugins.subcommands.run import Run

        logger.info(
            "[bold]Flux run requested[/]: nodes=%s, queue_timeout=%ss, time_limit=%ss",
            args.flux_nodes if args.flux_nodes is not None else "auto",
            args.flux_queue_timeout,
            args.flux_time_limit,
        )
        console_style = canary.config.getoption("console_style") or {}
        if "live_columns" not in console_style:
            console_style["live_columns"] = (
                "Job,ID,Status,Queued,Startup,Running,Teardown,Elapsed,Rank"
            )
        setattr(canary.config.options, "console_style", console_style)
        return Run().execute(args)


class FluxExec:
    """
    Implements:

        canary flux exec --session SESSION SPEC

    """

    @staticmethod
    def setup_parser(parser: "Parser") -> None:
        parser.set_defaults(banner=False, flux_exec=True, flux_direct_run=False)

        parser.add_argument("--session", required=True, help="Run the job in this session")

        parser.add_argument("spec", help="Run this spec ID")

    def execute(self, args: argparse.Namespace) -> int:
        return flux_exec(args)


@hookimpl(tryfirst=True)
def canary_resource_pool_fill(config: "CanaryConfig") -> dict[str, Any] | None:
    """
    Create a Canary resource pool from the root Flux/hpc_connect backend.

    This is independent of canary_hpc. It activates for `canary flux run`.
    """
    if config.getoption("flux_exec", False):
        return None

    if not config.getoption("flux_direct_run", False):
        return None

    import hpc_connect

    backend = hpc_connect.get_backend("flux")
    node_count = _flux_node_count(backend)
    resources_per_node = _flux_resources_per_node(backend)
    nodes: list[dict[str, Any]] = []
    for i in range(node_count):
        resources: dict[str, list[dict[str, Any]]] = {}
        for rtype, count in sorted(resources_per_node.items()):
            resources[rtype] = _resource_specs(count, rtype=rtype)
        nodes.append({"id": str(i), "resources": resources})
    pool = {
        "allow_multinode": node_count > 1,
        "additional_properties": {
            "source": "canary_flux",
            "backend": backend.name,
            "node_count": node_count,
            **{f"{rtype}_per_node": count for rtype, count in resources_per_node.items()},
        },
        "nodes": nodes,
    }
    logger.debug("Created Flux resource pool from backend %s: %r", backend.name, pool)
    return pool


@hookimpl(tryfirst=True)
def canary_runtests(runner: "Runner") -> bool | None:
    if not canary.config.getoption("flux_direct_run", False):
        return None

    from hpcc_flux.allocation import FluxAllocation

    from .executor import FluxDirectExecutor

    node_count = _allocation_node_count(runner.jobs)
    queue_timeout = float(canary.config.getoption("flux_queue_timeout") or 1200)
    time_limit = float(canary.config.getoption("flux_time_limit") or 3600)
    for job in runner.jobs:
        if (t := job.total_timeout()) > time_limit:
            time_limit = t

    logger.info(
        "[bold]Starting[/] Flux allocation for %d jobs: nodes=%d, "
        "queue_timeout=%.1fs, time_limit=%.1fs",
        len(runner.jobs),
        node_count,
        queue_timeout,
        time_limit,
    )

    with FluxAllocation(
        nodes=node_count, time_limit=time_limit, queue_timeout=queue_timeout
    ) as allocation:
        logger.info(
            "[bold]Flux allocation active[/]: jobid=%s uri=%s", allocation.jobid, allocation.uri
        )
        logger.info("[bold]FLUX_URI[/]: %s", os.environ.get("FLUX_URI"))

        executor = FluxDirectExecutor(runner)
        executor.run()

    logger.info("[bold]Flux allocation closed[/]")

    return True


def _allocation_node_count(jobs: list["canary.Job"]) -> int:
    requested = canary.config.getoption("flux_nodes")
    cli_nodes = int(requested) if requested is not None else 0
    job_nodes = 1
    for job in jobs:
        job_nodes = max(job_nodes, len(job.required_resources()))
    return max(cli_nodes, job_nodes, 1)


def _flux_node_count(backend: Any) -> int:
    """
    Best-effort node-count discovery from the root Flux backend.
    """
    for method_name in ("count", "resource_count"):
        method = getattr(backend, method_name, None)
        if method is None:
            continue

        for rtype in ("nodes", "node"):
            n = 0
            try:
                n = int(method(rtype))
            except Exception as e:
                logger.debug(
                    "Flux backend %s(%r) node-count query failed: %s", method_name, rtype, e
                )

            if n > 0:
                return n

    for name in ("FLUX_RESOURCE_NNODES", "FLUX_JOB_NNODES"):
        value = os.getenv(name)
        if not value:
            continue

        n = 0
        try:
            n = int(value)
        except ValueError as e:
            logger.debug("Invalid %s=%r: %s", name, value, e)

        if n > 0:
            return n

    return 1


def _flux_resources_per_node(backend: Any) -> dict[str, int]:
    """
    Best-effort per-node resource discovery from hpc_connect.
    """
    rtypes: set[str] = {"cpus", "gpus"}
    try:
        rtypes.update(_canonical_resource_type(rtype) for rtype in backend.resource_types())
    except Exception:
        logger.debug("Flux backend did not report resource_types()", exc_info=True)
    resources: dict[str, int] = {}
    for rtype in sorted(rtypes):
        count = _backend_count_per_node(backend, rtype)
        if rtype == "cpus" and count <= 0:
            count = 1
        if count > 0:
            resources[rtype] = count
    resources.setdefault("cpus", 1)
    resources.setdefault("gpus", 0)
    return resources


def _backend_count_per_node(backend: Any, rtype: str) -> int:
    candidates = [rtype]

    singular = _singular_resource_type(rtype)
    plural = _canonical_resource_type(rtype)

    for candidate in (singular, plural):
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        count = 0
        try:
            count = int(backend.count_per_node(candidate))
        except Exception as e:
            logger.debug("Flux backend count_per_node(%r) failed: %s", candidate, e)

        if count > 0:
            return count

    return 0


def _canonical_resource_type(rtype: str) -> str:
    return rtype if rtype.endswith("s") else f"{rtype}s"


def _singular_resource_type(rtype: str) -> str:
    return rtype[:-1] if rtype.endswith("s") else rtype


def _resource_specs(count: int, *, rtype: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for i in range(count):
        spec: dict[str, Any] = {"id": str(i), "slots": 1}
        if rtype == "gpus":
            spec["properties"] = {"vendor": "UNKNOWN"}
        specs.append(spec)
    return specs


def flux_exec(args: argparse.Namespace) -> int:
    """
    Execute one Canary job inside the active Flux allocation.

    This is modeled after `canary exec`, but writes the completed Job to the
    workspace database FSQueue instead of directly to SQLite.
    """
    import time

    from _canary import config
    from _canary.job import Job
    from _canary.workspace import Workspace

    workspace = Workspace.load()
    session_dir = workspace.sessions_dir / args.session

    spec = workspace.find_jobspec(args.spec)
    specs = workspace.db.load_specs(ids=[spec.id], include_upstreams=True)
    jobs = workspace.construct_jobs(specs, session_dir)

    job: Job = next(j for j in jobs if j.id == spec.id)

    # This execution is authoritative for this job.
    job.status.reset()
    job.state.reset()

    # The parent scheduler only submits ready jobs, but keep the guard.
    if not job.is_ready():
        job.refresh_readiness()
        if job.state.is_done():
            job.save()
            workspace.db.queue.put(job)
            return 0
        raise RuntimeError(f"{job}: job is not ready to run")

    # Fill Canary's view of resources from Flux environment before setup/run.
    assign_flux_resources(job)

    pm = config.pluginmanager.hook

    try:
        now = time.time()
        job.timekeeper.submitted = now

        pm.canary_runteststart(case=job)

        now = time.time()
        job.timekeeper.started = now

        pm.canary_runtest(case=job)

        job.timekeeper.finished = time.time()

    finally:
        pm.canary_runtest_finish(case=job)
        job.save()

        # Key difference from `canary exec`: write to FSQueue, not SQLite.
        workspace.db.queue.put(job)

    # Return a useful process code. Canary Status already encodes outcome.
    return int(job.status.code if job.status.code is not None else 0)


def assign_flux_resources(job: "canary.Job") -> None:
    """
    Best-effort resource assignment from Flux environment.

    For now, use visible GPU env vars if present. CPU assignment can be added
    after we confirm the basic path.
    """
    resources: dict[str, list[dict]] = {}

    gpu_ids = _visible_gpu_ids()
    if gpu_ids:
        resources["gpus"] = [
            {"node": os.getenv("FLUX_JOB_ID", "0"), "id": gpu_id, "slots": 1} for gpu_id in gpu_ids
        ]

    # Optional simple CPU placeholder. If tests rely on CANARY_CPU_IDS, we can
    # improve this using Flux-provided cpuset information later.
    cpus = int(job.cpus or 1)
    resources["cpus"] = [
        {"node": os.getenv("FLUX_JOB_ID", "0"), "id": str(i), "slots": 1} for i in range(cpus)
    ]

    job.assign_resources(
        {
            "metadata": {
                "source": "canary_flux",
                "flux_job_id": os.getenv("FLUX_JOB_ID"),
                "flux_uri": os.getenv("FLUX_URI"),
            },
            "resources": resources,
        }
    )


def _visible_gpu_ids() -> list[str]:
    for name in (
        "CUDA_VISIBLE_DEVICES",
        "ROCR_VISIBLE_DEVICES",
        "HIP_VISIBLE_DEVICES",
        "GPU_DEVICE_ORDINAL",
    ):
        value = os.getenv(name)
        if value:
            return [item.strip() for item in value.split(",") if item.strip()]
    return []
