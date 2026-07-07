# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse

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
            server = args.canary_dist_server_url
            conductor = DistributedPoolConductor(server_url=server)
            state = conductor.pool_state()
            print_resource_pool_status(state["database"])
            return 0
        elif args.dist_cmd == "run":
            server = args.canary_dist_server_url
            conductor = DistributedPoolConductor(server_url=server)
            conductor.register(canary.config.pluginmanager)
            return conductor.run(args)
        elif args.dist_cmd == "exec":
            executor = DistributedPoolExecutor(workspace=args.canary_dist_workspace)
            executor.register(canary.config.pluginmanager)
            return executor.run(args)
        return 0


@canary.hookimpl
def canary_addcommand(parser: "canary.Parser") -> None:
    parser.add_command(Distributed())


@canary.hookimpl(tryfirst=True)
def canary_hpc_batch_runner(batch, backend) -> "HPCConnectDistRunner | None":
    from .batchexec import HPCConnectDistRunner

    if hasattr(batch, "hostname") and backend.name == "remote_subprocess":
        return HPCConnectDistRunner(backend)
