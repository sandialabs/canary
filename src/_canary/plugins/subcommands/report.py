# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
from argparse import Namespace
from typing import TYPE_CHECKING

from ...util import logging
from ..hookspec import hookimpl
from ..types import CanaryReport
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Report()


class Report(CanarySubcommand):
    name = "report"
    description = "Create and post test reports"

    def setup_parser(self, parser: "Parser") -> None:
        from ... import config

        parser.epilog = self.in_session_note()
        subparsers = parser.add_subparsers(dest="type", metavar="subcommands")
        for report in config.plugin_manager.hook.canary_session_report():
            parent = subparsers.add_parser(report.type, help=report.description)
            report.setup_parser(parent)

    def execute(self, args: Namespace) -> int:
        from ... import config
        from ...session import NotASession
        from ...session import Session

        report: CanaryReport
        for report in config.plugin_manager.hook.canary_session_report():
            if report.type == args.type:
                break
        else:
            raise ValueError(f"canary report: unknown report type {args.type!r}")

        session: Session | None
        try:
            with logging.level(logging.WARNING):
                session = Session(os.getcwd(), mode="r")
        except NotASession:
            session = None
        kwargs = vars(args)
        action = getattr(report, args.action.replace("-", "_"), report.not_implemented)
        action(session, **kwargs)
        return 0
