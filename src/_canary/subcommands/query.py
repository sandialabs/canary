# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..hookspec import hookimpl
from ..util.query_data import list_json_object_paths
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
from ..util.query_data import query_json
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


class Query(CanarySubcommand):
    name = "query"
    description = "Query Canary job or session lock files"

    def setup_parser(self, parser: "Parser") -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "-j", "--job", dest="jobid", metavar="JOBID", help="Query the testcase.lock for JOBID"
        )
        group.add_argument(
            "-s",
            "--session",
            dest="session",
            metavar="SESSION",
            help="Query the session.lock for SESSION",
        )
        parser.add_argument("--terse", action="store_true", help="Print compact single-line JSON")
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_keys",
            help="List queryable object keys below the selected query point",
        )
        parser.add_argument(
            "query",
            nargs="?",
            default=".",
            help="Query expression. If omitted, emit the whole selected JSON object.",
        )

    def execute(self, args: argparse.Namespace) -> int:
        workspace = Workspace.load()

        if args.jobid:
            lockfile = self.job_lockfile(workspace, args.jobid)
        else:
            lockfile = self.session_lockfile(workspace, args.session)

        data = json.loads(lockfile.read_text())

        if args.list_keys:
            print_query_paths(list_json_object_paths(data, args.query))
            return 0

        result = query_json(data, args.query)
        print_json(result, terse=args.terse)
        return 0

    def job_lockfile(self, workspace: Workspace, jobid: str) -> Path:
        job = workspace.find_job(jobid)
        lockfile = job.lockfile
        if not lockfile.exists():
            raise FileNotFoundError(lockfile)
        return lockfile

    def session_lockfile(self, workspace: Workspace, session: str) -> Path:
        session_dir = self.resolve_session_dir(workspace, session)
        lockfile = session_dir / "session.lock"
        if not lockfile.exists():
            raise FileNotFoundError(lockfile)
        return lockfile

    def resolve_session_dir(self, workspace: Workspace, session: str) -> Path:
        if session == "latest":
            latest = workspace.refs_dir / "latest"
            if not latest.exists():
                raise FileNotFoundError(latest)
            rel = latest.read_text().strip()
            return (workspace.refs_dir / rel).resolve()

        candidate = workspace.sessions_dir / session
        if candidate.is_dir():
            return candidate

        matches = sorted(p for p in workspace.sessions_dir.glob(f"{session}*") if p.is_dir())

        if not matches:
            raise ValueError(f"{session!r}: no matching session found")

        if len(matches) > 1:
            names = ", ".join(p.name for p in matches[:8])
            if len(matches) > 8:
                names += ", ..."
            raise ValueError(f"{session!r}: ambiguous session prefix; matches: {names}")

        return matches[0]


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Query())
