# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import canary
from _canary.plugins.subcommands.run import Run

from .argparsing import CanaryHPCBatchSpec
from .conductor import CanaryHPCConductor
from .executor import CanaryHPCExecutor

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_configure(config: "canary.Config") -> None:
    """Do some post configuration checks"""
    scheduler = config.getoption("canary_hpc_scheduler")
    command = config.getoption("command")
    if scheduler is not None and command == "run":
        # Run with the HPC conductor
        config.options.command = "hpc"
        config.options.hpc_cmd = "run"
        if not hasattr(config.options, "canary_hpc_batchspec"):
            # no batchspec was passed on the command line, so set the defaults
            setattr(config.options, "canary_hpc_batchspec", CanaryHPCBatchSpec.defaults())


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
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

        p = subparsers.add_parser("run", help="Batch test cases and submit to HPC scheduler")
        Run().setup_parser(p)
        group = p.add_argument_group(title="Batched execution options")
        CanaryHPCConductor.setup_parser(group)

        p = subparsers.add_parser("exec", help="Execute (run) the batch")
        CanaryHPCExecutor.setup_parser(p)

        p = subparsers.add_parser("help", help="Additional canary_hpc help topics")
        p.add_argument(
            "--spec",
            default=False,
            action="store_true",
            help="Help on the batch specification syntax",
        )

    def execute(self, args: argparse.Namespace) -> int:
        if args.hpc_cmd == "run":
            scheduler = args.canary_hpc_scheduler
            if scheduler is None:
                raise ValueError("canary hpc run requires --scheduler")
            conductor = CanaryHPCConductor(backend=scheduler)
            conductor.register(canary.config.pluginmanager)
            return conductor.run(args)
        elif args.hpc_cmd == "exec":
            # Batch is being executed within an allocation
            # register the CanaryHPCExector plugin so that executor.runtests is registered
            backend = args.canary_hpc_backend or canary.config.getoption("canary_hpc_scheduler")
            executor = CanaryHPCExecutor(
                workspace=args.canary_hpc_workspace, backend=backend, case=args.canary_hpc_case
            )
            executor.register(canary.config.pluginmanager)
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
