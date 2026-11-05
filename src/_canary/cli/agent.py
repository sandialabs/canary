# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ..agent import write_agent_bootstrap
from ..plugins.hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


class Agent(CanarySubcommand):
    name = "agent"
    description = "Bootstrap agent-facing Canary guidance and skills"

    def setup_parser(self, parser: "Parser") -> None:
        sub = parser.add_subparsers(dest="agent_command", metavar="SUBCMD")

        bootstrap = sub.add_parser("bootstrap", help="Write repo-local agent guidance files")
        bootstrap.add_argument(
            "target",
            nargs="?",
            choices=("generic", "opencode", "claude"),
            default="generic",
            help="Bootstrap target layout (default: generic)",
        )
        bootstrap.add_argument(
            "--brief", action="store_true", help="Write only the concise bootstrap file"
        )
        bootstrap.add_argument(
            "--force", action="store_true", help="Overwrite existing managed files"
        )
        bootstrap.add_argument(
            "--append",
            action="store_true",
            help="Append or refresh Canary guidance in an existing CLAUDE.md",
        )
        bootstrap.set_defaults(_agent_handler=self.run_bootstrap)

    def execute(self, args: argparse.Namespace) -> int:
        handler = getattr(args, "_agent_handler", None)
        if handler is None:
            epilog = (self.epilog or "").replace("[pad]", "  ")
            print(f"{self.description}.\n\n{epilog}")
            return 0
        return handler(args)

    def run_bootstrap(self, args: argparse.Namespace) -> int:
        write_agent_bootstrap(args.target, brief=args.brief, force=args.force, append=args.append)
        return 0


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Agent())
