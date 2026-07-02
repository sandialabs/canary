# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import canary
from _canary.plugins.subcommands.run import Run
from _canary.util.time import time_in_seconds

from .conductor import FluxConductor

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_addcommand(parser: canary.Parser) -> None:
    parser.add_command(CanaryFlux())


class CanaryFlux(canary.CanarySubcommand):
    name = "flux"
    description = "BETA: Bootstrap a `flux` allocation and use for the resource pool"

    def setup_parser(self, parser: canary.Parser):
        subparsers = parser.add_subparsers(dest="flux_cmd", title="subcommands", metavar="")
        p = subparsers.add_parser("run", help="Execute the tests under `flux`")
        Run().setup_parser(p)

        parser.add_argument(
            "--scheduler",
            metavar="SCHED",
            dest="canary_flux_scheduler",
            type=str,
            default="flux",
            help="Backend scheduler used to bootstrap the flux allocation (default: %(default)s)",
        )

        parser.add_argument(
            "--queue-timeout",
            metavar="T",
            dest="canary_flux_queue_timeout",
            type=time_in_seconds,
            default="20m",
            help="Maximum delay for the Flux allocation to start (default: %(default)s)",
        )

        parser.add_argument(
            "-N",
            "--nodes",
            metavar="N",
            dest="canary_flux_nodes",
            type=int,
            default=1,
            help="Number of nodes to request for the flux allocation (default: %(default)s)",
        )

        parser.add_argument(
            "-t",
            "--time-limit",
            metavar="T",
            dest="canary_flux_time_limit",
            type=time_in_seconds,
            default="60m",
            help="Time limit for the Flux allocation (default: %(default)s)",
        )

    def execute(self, args: argparse.Namespace) -> int:
        canary.config.pluginmanager.register(FluxConductor())
        return Run().execute(args)
