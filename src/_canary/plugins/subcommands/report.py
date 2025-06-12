# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
from argparse import Namespace
from typing import TYPE_CHECKING

from ...util import logging
from ..hookspec import hookimpl
from ..types import CanaryReporter
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
        for reporter in config.plugin_manager.hook.canary_session_reporter():
            parent = subparsers.add_parser(reporter.type, help=reporter.description)
            reporter.setup_parser(parent)

    def execute(self, args: Namespace) -> int:
        from ... import config
        from ...session import NotASession
        from ...session import Session

        reporter: CanaryReporter
        for reporter in config.plugin_manager.hook.canary_session_reporter():
            if reporter.type == args.type:
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
        action = getattr(reporter, args.action.replace("-", "_"), reporter.not_implemented)
        action(session, **kwargs)
        return 0
