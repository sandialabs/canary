# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import hpc_connect

import canary
from _canary.subcommands.run import Run
from _canary.util.query_data import load_query_data
from _canary.util.rich import bold

from .argparsing import CanaryHPCBatchSpec
from .conductor import CanaryHPCConductor
from .executor import CanaryHPCExecutor

if TYPE_CHECKING:
    from .batchexec import HPCConnectRunner
    from .batchspec import TestBatch


__all__ = ["CanaryHPCBatchSpec", "CanaryHPCConductor", "CanaryHPCExecutor"]

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_cmdline_modifyargs(parser: "canary.Parser", args: argparse.Namespace) -> None:
    """Do post-parse HPC argument normalization."""
    backend = getattr(args, "hpc_backend", None)

    if backend is not None and args.command == "run":
        # Run with the HPC conductor.
        args.command, args.hpc_cmd = "hpc", "run"

        raw_batchspec = getattr(args, "hpc_batchspec", None)

        if raw_batchspec is None:
            raw_batchspec = CanaryHPCBatchSpec.defaults()

        args.hpc_batchspec = CanaryHPCBatchSpec.validate_and_set_defaults(raw_batchspec)


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    parser.add_argument(
        "--hpc-backend",
        dest="hpc_backend",
        metavar="BACKEND",
        group="canary hpc",
        default=os.getenv("CANARY_HPC_BACKEND") or argparse.SUPPRESS,
        help="Use this HPC backend [default: None]",
    )
    CanaryHPCConductor.setup_legacy_parser(parser)


@canary.hookimpl
def canary_addcommand(parser: canary.Parser) -> None:
    parser.add_command(HPC())


@canary.hookimpl
def canary_query_subcommand(subparsers: "argparse._SubParsersAction") -> None:  # type: ignore[type-arg]
    """Register ``canary query batch`` and ``canary query batches``."""
    # ---- batch ----
    p_batch = subparsers.add_parser("batch", help="Query a batch.lock for a single HPC batch")
    p_batch.add_argument("batchid", metavar="BATCHID", help="Batch ID (7-char prefix or full UUID)")
    p_batch.add_argument(
        "path", nargs="?", default=".", help="JSON path expression (default: whole document)"
    )
    p_batch.add_argument("--clean", action="store_true", help="Strip __type__ wrappers")
    p_batch.add_argument("--terse", action="store_true", help="Compact single-line JSON")
    p_batch.add_argument(
        "--list",
        dest="list_keys",
        action="store_true",
        help="List queryable child keys at the selected path",
    )
    p_batch.add_argument(
        "--session",
        metavar="SESSION",
        default=None,
        help='Session name, prefix, or "latest" [default: latest]',
    )

    # ---- batches ----
    p_batches = subparsers.add_parser(
        "batches", help="List all batches for a session with job counts and timing"
    )
    p_batches.add_argument(
        "--session",
        metavar="SESSION",
        default="latest",
        help='Session name, prefix, or "latest" [default: latest]',
    )
    p_batches.add_argument(
        "--where",
        metavar="EXPR",
        default=None,
        help='Filter predicate, e.g. "status.outcome==PASS"',
    )
    p_batches.add_argument("--terse", action="store_true", help="Compact single-line JSON")


@canary.hookimpl
def canary_query_execute(args: "argparse.Namespace") -> "int | None":
    """Handle ``canary query batch`` and ``canary query batches``."""
    subcmd = getattr(args, "query_subcmd", None)
    if subcmd == "batch":
        return _exec_query_batch(args)
    if subcmd == "batches":
        return _exec_query_batches(args)
    return None


@canary.hookimpl
def canary_capabilities() -> dict[str, Any] | None:
    return load_query_data("canary_hpc.data", "capabilities.json")


@canary.hookimpl
def canary_skills() -> dict[str, Any] | None:
    return load_query_data("canary_hpc.data", "skills.json")


class HPC(canary.CanarySubcommand):
    name = "hpc"
    aliases = ["batch"]
    description = "Manage and run job batches on an HPC scheduler"

    def setup_parser(self, parser: canary.Parser):
        subparsers = parser.add_subparsers(dest="hpc_cmd", title="subcommands", metavar="")

        p = subparsers.add_parser("run", help="Batch jobs and submit to HPC scheduler")
        Run().setup_parser(p)
        p.update_argument(
            "--timeout",
            help=f"""\n
Slurm timeout types:\n\n
• type={bold("queue")}, maximum time to wait in the slurm queue before treating it as timed out.
""",
        )
        group = p.add_argument_group(title="Batched execution options")
        CanaryHPCConductor.setup_parser(group)

        p = subparsers.add_parser("exec", help="Execute (run) the batch")
        CanaryHPCExecutor.setup_parser(p)

        p = subparsers.add_parser("info", help="Show HPC scheduler basic info")
        p.add_argument("hpc_backend", metavar="backend", help="Show information on this backend")

        p = subparsers.add_parser("log", help="Print the batch log")
        p.add_argument("batch_id", nargs="?", help="Batch ID")

        p = subparsers.add_parser("help", help="Additional canary_hpc help topics")
        p.add_argument(
            "--spec",
            default=False,
            action="store_true",
            help="Help on the batch specification syntax",
        )

    def execute(self, args: argparse.Namespace) -> int:
        if args.hpc_cmd == "run":
            hpc_backend = getattr(args, "hpc_backend", None)
            if hpc_backend is None:
                raise ValueError("canary hpc run requires --backend")
            conductor = CanaryHPCConductor(backend=hpc_backend)
            conductor.register(canary.config.pluginmanager)
            return conductor.run(args)
        elif args.hpc_cmd == "info":
            backend: hpc_connect.Backend = hpc_connect.get_backend(args.hpc_backend)
            print(backend.describe())
            return 0
        elif args.hpc_cmd == "log":
            display_batch_log(args.batch_id)
        elif args.hpc_cmd == "exec":
            # Batch is being executed within an allocation
            # register the CanaryHPCExector plugin so that executor.runtests is registered
            backend_name = args.hpc_backend or canary.config.getoption("hpc_backend")
            executor = CanaryHPCExecutor(
                workspace=args.hpc_workspace, backend=backend_name, job=args.hpc_case
            )
            return executor.run(args)
        elif args.hpc_cmd == "help":
            self.extra_help(args)
        else:
            raise ValueError(f"canary hpc: unknown subcommand {args.hpc_cmd!r}")
        return 0

    def extra_help(self, args: argparse.Namespace) -> None:
        if args.spec:
            print(CanaryHPCBatchSpec.helppage())
        return


@canary.hookimpl(tryfirst=True)
def canary_resource_pool_fill(config: canary.Config) -> dict[str, Any] | None:
    command = config.getoption("hpc_cmd")
    if command == "exec":
        workspace = Path(config.getoption("hpc_workspace"))
        if not workspace.exists():
            raise ValueError(f"Workspace {workspace} does not exist")
        return fill_batch_resource_pool(workspace)
    backend = config.getoption("hpc_backend")
    if backend is None:
        return None
    _reject_canary_resource_overrides(config, backend)
    return fill_hpc_resource_pool(backend)


def _reject_canary_resource_overrides(config: canary.Config, backend: str) -> None:
    forbidden: list[str] = []
    if config.getoption("resource_pool_mods"):
        forbidden.append("-r/--resource-pool modifiers")
    if config.getoption("resource_pool_file"):
        forbidden.append("--resource-pool-file")
    if config.getoption("oversubscribe"):
        forbidden.append("--oversubscribe")
    if forbidden:
        opts = ", ".join(forbidden)
        raise ValueError(
            "Canary HPC mode requires the selected hpc_connect backend to define "
            f"the test resource pool. Resource-pool overrides are not allowed with "
            f"HPC backend {backend!r}: {opts}. "
            "Configure CPUs, GPUs, nodes, and other resources in the hpc_connect backend instead."
        )


def fill_batch_resource_pool(workspace: Path) -> dict[str, Any]:
    """Load the batch-local topology-aware resource pool."""
    f = workspace / "resource_pool.json"
    if not f.exists():
        raise FileNotFoundError(f"Missing batch resource pool file: {f}")
    fd = json.loads(f.read_text())
    return fd["resource_pool"]


def fill_hpc_resource_pool(b: str) -> dict[str, Any]:
    """Create a topology-aware resource pool representing the HPC backend.

    Node IDs are virtual/backend-local bookkeeping IDs. Canary core does not
    need to know where the scheduler will physically place the job.
    """

    backend: hpc_connect.Backend = hpc_connect.get_backend(b)

    def _canonical_resource_type(rtype: str) -> str:
        return rtype if rtype.endswith("s") else f"{rtype}s"

    def _singular_resource_type(rtype: str) -> str:
        return rtype[:-1] if rtype.endswith("s") else rtype

    def _resource_specs(count: int, *, rtype: str) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for j in range(count):
            spec: dict[str, Any] = {"id": str(j), "slots": 1}
            if rtype == "gpus":
                spec["properties"] = {"vendor": "UNKNOWN"}
            specs.append(spec)
        return specs

    def _count_per_node(arg: str) -> int:
        nonlocal backend
        try:
            return backend.count_per_node(arg)
        except ValueError:
            try:
                return backend.count_per_node(_singular_resource_type(arg))
            except ValueError:
                return 0

    resource_types = {_canonical_resource_type(rtype) for rtype in backend.resource_types()}
    resource_types.update({"cpus", "gpus"})
    nodes: list[dict[str, Any]] = []
    for i in range(backend.node_count):
        resources: dict[str, list[dict[str, Any]]] = {}
        for rtype in sorted(resource_types):
            resources[rtype] = _resource_specs(_count_per_node(rtype), rtype=rtype)
        nodes.append({"id": str(i), "resources": resources})
    props = {"hpc_backend": backend.name, "source": "canary hpc", "node_count": backend.node_count}
    return {"allow_multinode": True, "additional_properties": props, "nodes": nodes}


# ---------------------------------------------------------------------------
# canary query batch / batches implementation helpers
# ---------------------------------------------------------------------------


def _resolve_batch_dir(workspace: "Any", session_arg: "str | None", batch_id: str) -> "Path":
    """Return the directory for a specific batch, resolving session if needed."""
    from _canary.subcommands.query import _resolve_session_dir

    if session_arg is None:
        # Search all sessions for this batch ID prefix.
        candidates = sorted(workspace.sessions_dir.glob(f"*/batches/{batch_id}*"))
        if not candidates:
            raise FileNotFoundError(
                f"No batch matching {batch_id!r} found under {workspace.sessions_dir}"
            )
        return candidates[0]

    session_dir = _resolve_session_dir(workspace, session_arg)
    candidates = sorted((session_dir / "batches").glob(f"{batch_id}*"))
    if not candidates:
        raise FileNotFoundError(
            f"No batch matching {batch_id!r} found in session {session_dir.name!r}"
        )
    return candidates[0]


def _exec_query_batch(args: "argparse.Namespace") -> int:
    """Implement ``canary query batch <BATCHID> [path]``."""
    from _canary.subcommands.query import _clean
    from _canary.util.query_data import list_json_object_paths
    from _canary.util.query_data import print_json
    from _canary.util.query_data import print_query_paths
    from _canary.util.query_data import query_json
    from _canary.workspace import Workspace

    workspace = Workspace.load()
    batch_dir = _resolve_batch_dir(workspace, getattr(args, "session", None), args.batchid)
    lockfile = batch_dir / "batch.lock"
    if not lockfile.exists():
        sys.stderr.write(f"canary query batch: batch.lock not found at {lockfile}\n")
        return 1

    data = json.loads(lockfile.read_text())
    path = getattr(args, "path", ".")

    if getattr(args, "list_keys", False):
        print_query_paths(list_json_object_paths(data, path))
        return 0

    result = query_json(data, path)
    if getattr(args, "clean", False):
        result = _clean(result)
    print_json(result, terse=getattr(args, "terse", False))
    return 0


def _exec_query_batches(args: "argparse.Namespace") -> int:
    """Implement ``canary query batches [--session S] [--where EXPR]``."""
    import datetime

    from _canary.subcommands.query import _parse_where
    from _canary.subcommands.query import _resolve_session_dir
    from _canary.util.query_data import print_json
    from _canary.workspace import Workspace

    workspace = Workspace.load()
    session_arg = getattr(args, "session", "latest")
    session_dir = _resolve_session_dir(workspace, session_arg)
    batches_dir = session_dir / "batches"

    if not batches_dir.exists():
        print_json([], terse=getattr(args, "terse", False))
        return 0

    # Collect all job IDs across every batch in this session so we can do a
    # single DB lookup instead of one query per batch.
    all_job_ids: list[str] = []
    batch_data: list[tuple] = []  # (batch_dir, data) pairs
    for batch_dir in sorted(batches_dir.iterdir()):
        lockfile = batch_dir / "batch.lock"
        if not lockfile.exists():
            continue
        data = json.loads(lockfile.read_text())
        batch_data.append((batch_dir, data))
        all_job_ids.extend(data.get("jobs", []))

    # Build id → name map from DB; fall back gracefully if DB is unavailable.
    id_to_name: dict[str, str] = {}
    if all_job_ids:
        try:
            workspace.db.connect()
            results = workspace.db.get_results(ids=all_job_ids)
            for spec_id, row in results.items():
                id_to_name[spec_id] = row.get("spec_name", spec_id[:7])
        except Exception:
            pass
        finally:
            workspace.db.close()

    rows = []
    for batch_dir, data in batch_data:
        # Build a summary row
        tk = data.get("timekeeper", {})
        if isinstance(tk, str):
            try:
                tk = json.loads(tk)
            except Exception:
                tk = {}
        submitted = tk.get("_submitted", -1)
        started = tk.get("_started", -1)
        stopped = tk.get("_stopped", -1)
        total = (stopped - submitted) if submitted > 0 and stopped > 0 else None
        queue_wait = (started - submitted) if submitted > 0 and started > 0 else None
        running = (stopped - started) if started > 0 and stopped > 0 else None

        raw_status = data.get("status", {})
        if isinstance(raw_status, str):
            try:
                raw_status = json.loads(raw_status)
            except Exception:
                raw_status = {}

        sm = data.get("schedule_metadata", {})

        job_ids: list[str] = data.get("jobs", [])
        jobs = [
            {"id": jid, "name": id_to_name.get(jid, jid[:7])}
            for jid in job_ids
        ]

        row = {
            "id": data.get("id", batch_dir.name),
            "id_prefix": batch_dir.name,
            "session": data.get("session", session_dir.name),
            "job_count": len(job_ids),
            "jobs": jobs,
            "estimated_runtime": data.get("estimated_runtime"),
            "algorithm": sm.get("algorithm"),
            "node_count": sm.get("node_count"),
            "width": sm.get("width"),
            "status": {
                "category": raw_status.get("category"),
                "outcome": raw_status.get("outcome"),
                "reason": raw_status.get("reason"),
            },
            "timings": {
                "total": round(total, 3) if total is not None else None,
                "queue_wait": round(queue_wait, 3) if queue_wait is not None else None,
                "running": round(running, 3) if running is not None else None,
            },
            "submitted_on": (
                datetime.datetime.fromtimestamp(submitted).isoformat() if submitted > 0 else None
            ),
        }
        rows.append(row)

    # Sort by job count descending so heaviest batches come first.
    rows.sort(key=lambda r: -(r["job_count"] if isinstance(r["job_count"], int) else 0))

    where = getattr(args, "where", None)
    if where:
        predicate = _parse_where(where)
        rows = [r for r in rows if predicate(r)]

    print_json(rows, terse=getattr(args, "terse", False))
    return 0


def display_batch_log(id: str) -> None:
    import pydoc

    from _canary.workspace import Workspace

    workspace = Workspace.load()
    # Search all sessions for a batch matching the given ID prefix.
    candidates = sorted(workspace.sessions_dir.glob(f"*/batches/{id}*"))
    if not candidates:
        raise FileNotFoundError(f"No batch matching {id!r} found under {workspace.sessions_dir}")
    d = candidates[0]
    file = d / "canary-out.txt"
    print(f"{file}:")
    if not file.exists():
        raise FileNotFoundError(file)
    pydoc.pager(file.read_text())


class CanaryHPCHooks:
    @staticmethod
    @canary.hookspec(firstresult=True)
    def canary_hpc_batch_runner(
        batch: "TestBatch", backend: hpc_connect.Backend
    ) -> "HPCConnectRunner":
        """Return a runner for this batch"""
        raise NotImplementedError


@canary.hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager"):
    pluginmanager.add_hookspecs(CanaryHPCHooks)


@canary.hookimpl(trylast=True, specname="canary_hpc_batch_runner")
def default_runner(batch: "TestBatch", backend: hpc_connect.Backend) -> "HPCConnectRunner | None":
    """Default implementation"""
    from .batchexec import HPCConnectBatchRunner

    return HPCConnectBatchRunner(backend)
