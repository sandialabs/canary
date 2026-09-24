# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""``canary tui`` -- launch the interactive workspace explorer."""

import argparse
from typing import TYPE_CHECKING

from ..plugins.hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Tui())


class Tui(CanarySubcommand):
    """Interactive terminal explorer for the current workspace's jobs and results."""

    name = "tui"
    description = "Explore the current workspace interactively in the terminal"

    def setup_parser(self, parser: "Parser") -> None:
        """Register ``paths`` (optional discover-and-run), ``--refresh``, ``--once``."""
        parser.add_argument(
            "paths",
            nargs="*",
            metavar="PATH",
            help="Optional test paths to discover and run on launch, then explore "
            "(like 'canary run PATH...' but inside the TUI). With no paths, open "
            "the existing workspace.",
        )
        parser.add_argument(
            "--refresh",
            type=float,
            default=2.0,
            metavar="SECONDS",
            help="Seconds between automatic data refreshes [default: 2.0]",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            default=False,
            help="Render a single frame and exit (non-interactive)",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        from .. import tui
        from ..app.pathspec import classify_pathspec
        from ..error import StopExecution
        from ..session.workspace import NotAWorkspaceError

        request = None
        if getattr(args, "paths", None):
            # Turn the positional paths into a run request (the same classifier
            # 'canary run' uses), so 'canary tui examples' discovers and runs the
            # tests under 'examples' and then drops into the live explorer.
            builder = classify_pathspec(list(args.paths))
            if builder.errors:
                raise StopExecution("; ".join(str(e) for e in builder.errors), 1)
            request = builder.finalize()

        try:
            return tui.run(refresh_interval=args.refresh, once=args.once, request=request)
        except NotAWorkspaceError:
            raise StopExecution("canary tui must be run inside a workspace", 1) from None
