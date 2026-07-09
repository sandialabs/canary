# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import hpc_connect

import canary
from _canary.plugins.subcommands.run import Run

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
    """Do some post configuration checks"""
    backend = getattr(args, "hpc_backend", None)
    if backend is not None and args.command == "run":
        # Run with the HPC conductor
        args.command, args.hpc_cmd = "hpc", "run"
        if not hasattr(args, "hpc_batchspec"):
            # no batchspec was passed on the command line, so set the defaults
            args.hpc_batchspec = CanaryHPCBatchSpec.defaults()


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


class HPC(canary.CanarySubcommand):
    name = "hpc"
    aliases = ["batch"]
    description = "Manage and run job batches on an HPC scheduler"

    def setup_parser(self, parser: canary.Parser):
        subparsers = parser.add_subparsers(dest="hpc_cmd", title="subcommands", metavar="")

        p = subparsers.add_parser("run", help="Batch jobs and submit to HPC scheduler")
        Run().setup_parser(p)
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
    return fill_hpc_resource_pool(backend)


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

    backend: hpc_connect.Backend = hpc_connect.get_backend(b)
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


def display_batch_log(id: str) -> None:
    import pydoc

    from _canary.workspace import Workspace

    workspace = Workspace.load()
    candidates = workspace.cache_dir.joinpath("canary-hpc/batches").glob(f"{id}*")
    d = next(candidates)
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
