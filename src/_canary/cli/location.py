# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

from .. import app
from ..app.failure_analysis import list_existing_logs
from ..app.paths import remap_path
from ..plugins.hookspec import hookimpl
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Location())


class Location(CanarySubcommand):
    name = "location"
    description = "Print locations of test files and directories"
    epilog = """\
If no options are give, -x is assumed."""

    def setup_parser(self, parser: "Parser") -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "-i",
            dest="show_input",
            action="store_true",
            default=False,
            help="Show the location of the test's input file",
        )
        group.add_argument(
            "-l",
            dest="show_log",
            action="store_true",
            default=False,
            help="Show the location of the test's log file",
        )
        group.add_argument(
            "-x",
            dest="show_working_directory",
            action="store_true",
            default=False,
            help="Show the location of the test's working directory",
        )
        group.add_argument(
            "-s",
            dest="show_source_dir",
            action="store_true",
            default=False,
            help="Show the location of the test's source directory",
        )
        parser.add_argument("--remap", default="auto", help="Path remapping mode")
        parser.add_argument("--json", action="store_true", default=False, help="Emit JSON output")
        parser.add_argument("testspec", nargs="+", help="Test name or test id")

    def execute(self, args: argparse.Namespace) -> int:
        from ..core.job import Job
        from ..core.jobspec import JobSpec

        workspace = app.open_workspace()
        root_at_creation = None
        latest = workspace.refs_dir / "latest"
        if latest.exists():
            lock = workspace.sessions_dir / latest.read_text().strip() / "session.lock"
            if lock.exists():
                root_at_creation = json.loads(lock.read_text()).get("root_at_creation")
        items = []
        testspecs = args.testspec if isinstance(args.testspec, list) else [args.testspec]
        for testspec in testspecs:
            f: Path | str
            if args.show_input or args.show_source_dir:
                spec: JobSpec = workspace.find(spec=testspec)
                f = spec.file if args.show_input else spec.file.parent
                items.append(
                    {
                        "id": spec.id,
                        "path": remap_path(
                            f, root_at_creation=root_at_creation, current_root=workspace.root.parent
                        ),
                    }
                )
            else:
                job: Job = workspace.find(job=testspec)
                if args.show_log:
                    logs = list_existing_logs(job)
                    f = Path(logs[0]["path"]) if logs else job.workspace.joinpath(job.stdout)
                else:
                    if (view := workspace.latest_view()) and (view.dir / job.view_path).exists():
                        f = view.dir / job.view_path
                    else:
                        f = job.workspace.dir
                items.append(
                    {
                        "id": job.id,
                        "path": remap_path(
                            f, root_at_creation=root_at_creation, current_root=workspace.root.parent
                        ),
                    }
                )
        if getattr(args, "json", False):
            json.dump(items, fp=__import__("sys").stdout, indent=2)
            __import__("sys").stdout.write("\n")
            return 0
        for item in items:
            print(item["path"])
        return 0
