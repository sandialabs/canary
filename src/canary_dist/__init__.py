# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import json
import os
from pathlib import Path
from typing import Any

import canary

from .batchexec import HPCConnectDistRunner
from .conductor import DistributedPoolConductor
from .executor import DistributedPoolExecutor
from .status import print_resource_pool_status

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_cmdline_modifyargs(parser: "canary.Parser", args: argparse.Namespace) -> None:
    """Do some post configuration checks"""
    command = getattr(args, "command", None)
    subcommand = getattr(args, "dist_cmd", None)
    if command == "dist" and subcommand in ("run", "status"):
        DistributedPoolConductor.validate_and_set_defaults(args)


class Distributed(canary.CanarySubcommand):
    name = "dist"
    description = "Manage testing across a distributed pool of machines"

    def setup_parser(self, parser: "canary.Parser") -> None:
        subparsers = parser.add_subparsers(metavar="", dest="dist_cmd", title="subcommands")

        p = subparsers.add_parser("status", help="Show the status of machines in pool")
        DistributedPoolConductor.add_server_argument(p)

        p = subparsers.add_parser("run", help="Run test cases across the distributed pool")
        DistributedPoolConductor.setup_parser(p)

        p = subparsers.add_parser("exec", help="Execute batch on remote machine")
        DistributedPoolExecutor.setup_parser(p)

    def execute(self, args):
        if args.dist_cmd == "status":
            server = args.dist_server_url
            conductor = DistributedPoolConductor(server_url=server)
            state = conductor.pool_state()
            print_resource_pool_status(state["database"])
            return 0
        elif args.dist_cmd == "run":
            server = args.dist_server_url
            conductor = DistributedPoolConductor(server_url=server)
            conductor.register(canary.config.pluginmanager)
            return conductor.run(args)
        elif args.dist_cmd == "exec":
            executor = DistributedPoolExecutor(workspace=args.dist_workspace)
            return executor.run(args)
        return 0


@canary.hookimpl
def canary_addoption(parser: canary.Parser) -> None:
    parser.add_argument(
        "--dist-server-url",
        dest="dist_server_url",
        metavar="URL",
        default=os.getenv("CANARY_DIST_SERVER_URL"),
        help="Distributed pool server location (URL). "
        "Defaults to CANARY_DIST_SERVER_URL environment variable, if defined.",
    )


@canary.hookimpl
def canary_addcommand(parser: "canary.Parser") -> None:
    parser.add_command(Distributed())


@canary.hookimpl(tryfirst=True)
def canary_hpc_batch_runner(batch, backend) -> "HPCConnectDistRunner | None":
    from .batchexec import HPCConnectDistRunner

    if hasattr(batch, "hostname") and backend.name == "remote_subprocess":
        return HPCConnectDistRunner(backend)


@canary.hookimpl(tryfirst=True)
def canary_resource_pool_fill(config: canary.Config) -> dict[str, Any] | None:
    command = config.getoption("dist_cmd")
    if command == "exec":
        workspace = Path(config.getoption("dist_workspace"))
        if not workspace.exists():
            raise ValueError(f"Workspace {workspace} does not exist")
        return fill_local_resource_pool(workspace)
    server = config.getoption("dist_server_url")
    if server is None:
        return None
    return fill_dist_resource_pool(server)


def fill_local_resource_pool(workspace: Path) -> dict[str, Any]:
    """Load the batch-local topology-aware resource pool."""
    f = workspace / "resource_pool.json"
    if not f.exists():
        raise FileNotFoundError(f"Missing batch resource pool file: {f}")
    fd = json.loads(f.read_text())
    return fd["resource_pool"]


def fill_dist_resource_pool(server_url: str) -> dict[str, Any]:
    from .adapter import DistributedResourcePoolAdapter

    dpool = DistributedResourcePoolAdapter(server_url=server_url)
    return dpool.to_resource_pool()
