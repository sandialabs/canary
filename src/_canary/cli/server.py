# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""``canary server``: run a workspace's request server (:mod:`_canary.service.fs`).

``canary server start`` runs a server for the current workspace in the foreground (use
``nohup canary server start &`` to keep one running after the terminal closes) and
``canary server stop`` stops it.  Callers need no canary: they drop typed requests into
``.canary/var/server/inbox/`` and read the results under ``requests/<id>/`` (see
:mod:`_canary.service.fs.inbox` and :mod:`_canary.api.dispatch`).
"""

import argparse
import os
from typing import TYPE_CHECKING

from ..plugins.hookspec import hookimpl
from ..service.fs import server
from ..util import logging
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..config.config import Config

logger = logging.get_logger(__name__)


class ServerCommand(CanarySubcommand):
    name = "server"
    description = "Run and manage this workspace's request server"

    def setup_parser(self, parser: "Parser") -> None:
        sub = parser.add_subparsers(dest="server_cmd", metavar="", title="subcommands")
        p = sub.add_parser(
            "start", help="Run the server for this workspace (blocks; background it with the shell)"
        )
        p.set_defaults(banner_default=True)  # the server's terminal is long-lived: greet it
        p.add_argument(
            "-w",
            dest="wipe",
            action="store_true",
            help="Remove the workspace here (if any) and start with a fresh one",
        )
        sub.add_parser("stop", help="Stop the server (interrupts the running request)")

    def execute(self, args: argparse.Namespace) -> int:
        if args.server_cmd == "start":
            server.Server(_start_root(args)).run()
            return 0
        if args.server_cmd == "stop":
            from ..workspace.workspace import Workspace

            if server.stop(Workspace.load().root):
                logger.info("[bold]Stopped[/] canary server")
            else:
                logger.info("No canary server is running for this workspace")
            return 0
        raise ValueError("canary server: expected start or stop")


@hookimpl
def canary_addconfig(config: "Config") -> None:
    from schema import Optional
    from schema import Schema

    from ..config.schemas import positive_int

    config.add_section(
        name="server",
        schema=Schema(
            {
                Optional("retain_days"): positive_int,
                Optional("read_workers"): positive_int,
                Optional("read_timeout"): positive_int,
                Optional("allowed_roots"): {str: str},
            }
        ),
    )


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(ServerCommand())


@hookimpl
def canary_capabilities() -> dict | None:
    from ..util.query_data import load_query_data

    return load_query_data("canary.data", "server-capabilities.json")


@hookimpl
def canary_skills() -> dict | None:
    from ..util.query_data import load_query_data

    return load_query_data("canary.data", "server-skills.json")


def _start_root(args: argparse.Namespace):
    """The workspace ``server start`` serves, created (or, with ``-w``, recreated) if needed.

    Like ``canary run``: the workspace found from here is used, or one is created here;
    ``-w`` removes only the workspace located exactly here (never an enclosing one) and
    creates a fresh one -- but never one a live server owns.
    """
    from ..workspace.workspace import NotAWorkspaceError
    from ..workspace.workspace import Workspace

    where = os.getcwd()
    if getattr(args, "wipe", False):
        existing = Workspace.workspace_at(where)
        if existing is None and (anchor := Workspace.find_anchor(start=where)) is not None:
            raise ValueError(
                f"-w: {where} is inside the workspace at {anchor}, which will not be wiped "
                f"implicitly.  Run from {anchor} or use 'canary rm {anchor}' first."
            )
        Workspace.detach(where)
        return Workspace.create(path=where).root
    try:
        return Workspace.load(start=where).root
    except NotAWorkspaceError:
        logger.info(f"[bold]Creating[/] a canary workspace in {os.path.abspath(where)}")
        return Workspace.create(path=where).root
