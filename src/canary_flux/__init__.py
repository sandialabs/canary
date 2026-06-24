# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import canary
from _canary.plugins.subcommands.run import Run

from .conductor import FluxConductor

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_addcommand(parser: canary.Parser) -> None:
    parser.add_command(CanaryFlux())


class CanaryFlux(canary.CanarySubcommand):
    name = "flux"
    description = "Bootstrap a `flux` subscheduler and use for the resource pool"

    def setup_parser(self, parser: canary.Parser):
        subparsers = parser.add_subparsers(dest="flux_cmd", title="subcommands", metavar="")
        p = subparsers.add_parser("run", help="Execute the tests under `flux`")
        Run().setup_parser(p)

    def execute(self, args: argparse.Namespace) -> int:
        canary.config.pluginmanager.register(FluxConductor())
        return Run().execute(args)
