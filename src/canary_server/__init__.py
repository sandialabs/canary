# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""canary_server: a workspace's file-based command server.

``canary server start`` runs a server for the current workspace; its state lives in
``.canary/var/server/`` (see :mod:`canary_server.server`).  Requests are handled one at a
time, each in its own ``canary`` child process.
"""

import argparse
import json

import canary

from . import server

logger = canary.get_logger(__name__)


class ServerCommand(canary.CanarySubcommand):
    name = "server"
    description = "Run and manage this workspace's command server"

    def setup_parser(self, parser: "canary.Parser") -> None:
        sub = parser.add_subparsers(dest="server_cmd", metavar="", title="subcommands")
        p = sub.add_parser("start", help="Start the server for this workspace")
        p.add_argument(
            "--foreground", action="store_true", help="Run in this process instead of detaching"
        )
        sub.add_parser("stop", help="Stop the server for this workspace")
        p = sub.add_parser("status", help="Show whether the server is running")
        p.add_argument("--json", action="store_true", help="Emit JSON")

    def execute(self, args: argparse.Namespace) -> int:
        from _canary.workspace.workspace import Workspace

        root = Workspace.load().root
        if args.server_cmd == "start":
            if args.foreground:
                server.Server(root).run()
                return 0
            info = server.start_in_background(root)
            logger.info(f"[bold]Started[/] canary server (pid {info.pid} on {info.host})")
            return 0
        if args.server_cmd == "stop":
            if server.stop(root):
                logger.info("[bold]Stopped[/] canary server")
            else:
                logger.info("No canary server is running for this workspace")
            return 0
        if args.server_cmd == "status":
            info = server.read_info(root)
            alive = info is not None and info.is_alive()
            if args.json:
                print(json.dumps(info.to_dict() if info is not None else {"alive": False}))
            elif alive:
                assert info is not None
                print(f"running: pid {info.pid} on {info.host}, version {info.version}")
            else:
                print("not running")
            return 0 if alive else 1
        raise ValueError("canary server: expected one of start, stop, status")


@canary.hookimpl
def canary_addcommand(parser: "canary.Parser") -> None:
    parser.add_command(ServerCommand())
