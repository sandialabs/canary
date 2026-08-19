# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import math
import os
from typing import TYPE_CHECKING
from typing import Any

import canary
from _canary.config.argparsing import append_option_help
from _canary.hookspec import hookimpl
from _canary.util.rich import bold
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
            "--submit-arg",
            dest="flux_submit_args",
            action="append",
            default=None,
            metavar="ARG",
            help="Additional argument passed to inner Flux/hpc_connect job submission; may be repeated",
        )
        group.add_argument(
            "--allocation-arg",
            dest="flux_alloc_args",
            action="append",
            default=None,
            metavar="ARG",
            help="Additional argument passed to Flux/hpc_connect allocation request; may be repeated",
        )
        group.add_argument(
            "--max-concurrent-jobs",
            dest="flux_max_concurrent_jobs",
            type=int,
            default=None,
            metavar="N",
            help="Maximum number of concurrent jobs to commit to flux [default: 50]",
        )

        from _canary.plugins.subcommands.run import Run

        Run().setup_parser(parser)
        append_option_help(
            parser,
            "--timeout",
            f"""\n
Flux timeout types:\n\n
• type={bold("queue")}, maximum time to wait for the Flux allocation or submitted Flux job to
      start before treating it as timed out.\n\n
• type={bold("allocation")}, walltime requested for the outer Flux allocation.\n\n
""",
            marker="Flux timeout types:",
        )

    def execute(self, args: argparse.Namespace) -> int:
        from _canary.plugins.subcommands.run import Run

        logger.info(
            "[bold]Flux run requested[/]: nodes=%s, queue_timeout=%ss, time_limit=%ss",
            args.flux_nodes if args.flux_nodes is not None else "auto",
            allocation_queue_timeout(),
            allocation_time_limit(),
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
    resources_per_node = _flux_resources_per_node(backend)
    nodes: list[dict[str, Any]] = []
    node_count: int = int(config.getoption("flux_nodes") or backend.node_count)
    for i in range(node_count):
        resources: dict[str, list[dict[str, Any]]] = {}
        for rtype, count in sorted(resources_per_node.items()):
            resources[rtype] = _resource_specs(count, rtype=rtype)
        nodes.append({"id": str(i), "resources": resources})
    pool = {
        "allow_multinode": True,
        "additional_properties": {
            "source": "canary_flux",
            "backend": backend.name,
            "node_count": node_count,
            **{f"{rtype}_per_node": count for rtype, count in resources_per_node.items()},
        },
        "nodes": nodes,
    }
    logger.debug("Created Flux resource pool from backend %s", backend.name)
    return pool


@hookimpl(tryfirst=True)
def canary_runtests(runner: "Runner") -> bool | None:
    from hpcc_flux.allocation import FluxAllocation

    from .executor import FluxDirectExecutor

    if not canary.config.getoption("flux_direct_run", False):
        return None

    node_count = allocation_node_count(runner.jobs)
    queue_timeout = allocation_queue_timeout()
    time_limit = allocation_time_limit()

    logger.info(
        "[bold]Starting[/] Flux allocation for %d jobs: nodes=%d, "
        "queue_timeout=%.1fs, time_limit=%.1fs",
        len(runner.jobs),
        node_count,
        queue_timeout,
        time_limit,
    )

    alloc_args: list[str] = []
    if time_limit:
        alloc_args.append(f"--time-limit={minutes(time_limit)}")
    if extra_alloc_args := canary.config.getoption("flux_alloc_args"):
        alloc_args.extend(extra_alloc_args)
    allocation = FluxAllocation(nodes=node_count)
    with allocation.open(alloc_args, timeout=queue_timeout) as alloc:
        logger.info("[bold]Flux allocation active[/]: jobid=%s uri=%s", alloc.jobid, alloc.uri)
        executor = FluxDirectExecutor(runner)
        executor.run()
    logger.info("[bold]Flux allocation closed[/]")

    return True


def allocation_queue_timeout() -> float:
    return canary.config.get_timeout_option("queue") or 1200.0


def allocation_time_limit() -> float:
    # Return the allocation time limit in seconds
    if t := canary.config.get_timeout_option("allocation"):
        return float(t)
    if alloc_args := canary.config.getoption("flux_alloc_args"):
        p = argparse.ArgumentParser()
        p.add_argument("--time-limit", "-t", dest="qtime")
        a, _ = p.parse_known_args(alloc_args)
        if a.qtime:
            try:
                return float(a.qtime) * 60.0
            except:
                return time_in_seconds(a.qtime)
    if t := canary.config.get_timeout_option("session"):
        return float(t)
    return 3600.0


def allocation_node_count(jobs: list["canary.Job"]) -> int:
    node_count = canary.config.resource_manager.count("nodes")
    for job in jobs:
        job_node_count = len(job.required_resources())
        if job_node_count > node_count:
            raise ValueError(f"{job=} requires more nodes than exist in this flux resource pool")
    return node_count


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

        import json

        with job.workspace.openfile("env.json", "w") as fh:
            json.dump(dict(os.environ), fh, indent=2)

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

    if dinfo := _device_info():
        resources["gpus"] = [
            {"node": os.getenv("FLUX_JOB_ID", "0"), "id": id, "slots": 1} for id in dinfo.ids
        ]
        job.variables[dinfo.varname] = ",".join(dinfo.ids)

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
                "flux_jobid": os.getenv("FLUX_JOB_ID"),
                "flux_uri": os.getenv("FLUX_URI"),
            },
            "resources": resources,
        }
    )


def _device_info() -> argparse.Namespace | None:
    for name in (
        "CUDA_VISIBLE_DEVICES",
        "ROCR_VISIBLE_DEVICES",
        "HIP_VISIBLE_DEVICES",
        "GPU_DEVICE_ORDINAL",
    ):
        value = os.getenv(name)
        if value:
            return argparse.Namespace(
                varname=name, ids=[item.strip() for item in value.split(",") if item.strip()]
            )
    return None


def minutes(seconds: float) -> float:
    return math.ceil(float(seconds) / 60.0)
