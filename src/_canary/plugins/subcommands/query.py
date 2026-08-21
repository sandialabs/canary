# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ...hookspec import hookimpl
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


class Query(CanarySubcommand):
    name = "query"
    description = "Query Canary job/session lock files"

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
            "query",
            nargs="?",
            default=".",
            help="Query expression. If omitted, emit the whole lock file.",
        )

    def execute(self, args: argparse.Namespace) -> int:
        workspace = Workspace.load()

        if args.jobid:
            lockfile = self.job_lockfile(workspace, args.jobid)
        else:
            lockfile = self.session_lockfile(workspace, args.session)

        data = json.loads(lockfile.read_text())
        result = query_json(data, args.query)

        if args.terse:
            json.dump(result, sys.stdout, separators=(",", ":"))
        else:
            json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
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


def query_json(data: Any, query: str) -> Any:
    query = query.strip()

    if not query or query == ".":
        return data

    if not query.startswith("."):
        query = "." + query

    current = data

    for token in parse_query(query):
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise TypeError(
                    f"Cannot access key {token!r} on {type(current).__name__}; "
                    f"current value is not an object"
                )
            try:
                current = current[token]
            except KeyError:
                raise KeyError(format_missing_key_message(token, current)) from None

        elif isinstance(token, int):
            if not isinstance(current, list):
                raise TypeError(
                    f"Cannot access index {token} on {type(current).__name__}; "
                    f"current value is not an array"
                )
            try:
                current = current[token]
            except IndexError:
                n = len(current)
                raise IndexError(f"No such index: {token}. Array length is {n}.") from None

        else:
            raise TypeError(f"Unsupported query token: {token!r}")

    return current


def format_missing_key_message(key: str, current: dict[str, Any]) -> str:
    keys = sorted(str(k) for k in current.keys())

    if not keys:
        return f"No such key: {key!r}. Current object has no keys."

    preview = ", ".join(keys[:24])
    if len(keys) > 24:
        preview += ", ..."

    return f"No such key: {key!r}. Available keys: {preview}"


def parse_query(query: str) -> list[str | int]:
    tokens: list[str | int] = []
    i = 0

    while i < len(query):
        ch = query[i]

        if ch == ".":
            i += 1
            start = i

            while i < len(query) and query[i] not in ".[":
                i += 1

            if i > start:
                tokens.append(query[start:i])

            continue

        if ch == "[":
            token, i = parse_bracket(query, i)
            tokens.append(token)
            continue

        raise ValueError(f"Invalid query syntax at column {i + 1}: {query!r}")

    return tokens


def parse_bracket(query: str, i: int) -> tuple[str | int, int]:
    assert query[i] == "["
    j = i + 1

    if j >= len(query):
        raise ValueError(f"Unclosed bracket in query: {query!r}")

    if query[j] in ("'", '"'):
        quote = query[j]
        j += 1
        chars: list[str] = []

        while j < len(query):
            ch = query[j]

            if ch == "\\":
                if j + 1 >= len(query):
                    raise ValueError(f"Invalid escape in query: {query!r}")
                chars.append(query[j + 1])
                j += 2
                continue

            if ch == quote:
                j += 1
                if j >= len(query) or query[j] != "]":
                    raise ValueError(f"Expected closing bracket in query: {query!r}")
                return "".join(chars), j + 1

            chars.append(ch)
            j += 1

        raise ValueError(f"Unclosed quoted key in query: {query!r}")

    match = re.match(r"-?\d+", query[j:])
    if match:
        value = int(match.group(0))
        j += len(match.group(0))
        if j >= len(query) or query[j] != "]":
            raise ValueError(f"Expected closing bracket in query: {query!r}")
        return value, j + 1

    raise ValueError(f"Invalid bracket expression in query: {query!r}")


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Query())
