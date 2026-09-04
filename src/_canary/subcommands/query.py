# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""canary query — structured workspace inspection.

Subcommands
-----------
job <ID> [path]          Query a single job's testcase.lock
job <ID> --cache         Show per-job timing cache statistics
session <S> [path]       Query a session's session.lock
session <S> --expand-jobs  Join session job_ids to DB result rows
sessions                 List all sessions with summary statistics
db schema                Emit workspace database DDL as JSON
db stats                 Emit per-outcome counts and session summary
db "<SQL>"               Execute a read-only SQL query, return JSON rows

The built-in subcommands (job, session, sessions, db) are implemented as
``@hookimpl(trylast=True, specname="canary_query_execute")`` functions in
``_canary.hooks``.  Extension subcommands are registered via the
``canary_query_subcommand`` hook and dispatched via ``canary_query_execute``.

Common flags
------------
--clean     Strip __type__ wrappers and normalise enum values to strings
--terse     Compact single-line JSON output
--list      List immediate child keys at the selected query path
--where     Filter predicate for --expand-jobs / sessions  (key==value)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import canary

from ..hookspec import hookimpl
from ..util.query_data import list_json_object_paths
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
from ..util.query_data import query_json
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


# ---------------------------------------------------------------------------
# Entry point hook
# ---------------------------------------------------------------------------


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Query())


# ---------------------------------------------------------------------------
# Top-level command
# ---------------------------------------------------------------------------


class Query(CanarySubcommand):
    """Structured inspection of Canary workspace data via job, session, sessions, and db subcommands."""

    name = "query"
    description = (
        "Query Canary workspace data.\n\n"
        "Subcommands: job, session, sessions, db\n\n"
        "Examples:\n"
        "  canary query job abc1234\n"
        "  canary query job abc1234 status.outcome\n"
        "  canary query job abc1234 --cache\n"
        "  canary query session latest --expand-jobs\n"
        "  canary query session latest --expand-jobs --where status.outcome==FAILED\n"
        "  canary query sessions\n"
        "  canary query db stats\n"
        "  canary query db schema\n"
        '  canary query db "SELECT spec_name, status_outcome FROM results LIMIT 10"\n'
    )

    def setup_parser(self, parser: "Parser") -> None:
        """Register built-in and extension subparsers under ``canary query``."""
        sub = parser.add_subparsers(dest="query_subcmd", metavar="SUBCMD")

        # ---- job ----
        p_job = sub.add_parser("job", help="Query a job's testcase.lock")
        p_job.add_argument("jobid", metavar="JOBID", help="Job ID (prefix or full 64-char)")
        p_job.add_argument(
            "path", nargs="?", default=".", help="JSON path expression (default: whole document)"
        )
        p_job.add_argument("--cache", action="store_true", help="Show timing cache for this job")
        p_job.add_argument("--clean", action="store_true", help="Strip __type__ wrappers")
        p_job.add_argument("--terse", action="store_true", help="Compact single-line JSON")
        p_job.add_argument(
            "--list",
            dest="list_keys",
            action="store_true",
            help="List queryable child keys at the selected path",
        )

        # ---- session ----
        p_ses = sub.add_parser("session", help="Query a session lock or its jobs")
        p_ses.add_argument("session", metavar="SESSION", help='Session name, prefix, or "latest"')
        p_ses.add_argument(
            "path",
            nargs="?",
            default=".",
            help="JSON path expression (only used without --expand-jobs)",
        )
        p_ses.add_argument(
            "--expand-jobs",
            action="store_true",
            help="Join session job_ids to DB result rows and return a JSON array",
        )
        p_ses.add_argument(
            "--where",
            metavar="EXPR",
            help=(
                "Filter predicate for --expand-jobs, e.g. "
                '"status.outcome==FAILED" or "status.category==FAIL"'
            ),
        )
        p_ses.add_argument("--clean", action="store_true", help="Strip __type__ wrappers")
        p_ses.add_argument("--terse", action="store_true", help="Compact single-line JSON")
        p_ses.add_argument(
            "--list",
            dest="list_keys",
            action="store_true",
            help="List queryable child keys at the selected path",
        )

        # ---- sessions ----
        p_sessions = sub.add_parser("sessions", help="List all sessions with summary statistics")
        p_sessions.add_argument(
            "--where", metavar="EXPR", help='Filter predicate, e.g. "returncode==0"'
        )
        p_sessions.add_argument("--terse", action="store_true", help="Compact single-line JSON")

        # ---- db ----
        p_db = sub.add_parser("db", help="Query the workspace SQLite database")
        p_db.add_argument(
            "db_args",
            nargs=argparse.REMAINDER,
            metavar="ARG",
            help=(
                'One of: "schema", "stats", or a SQL SELECT statement '
                '(e.g. "SELECT * FROM results LIMIT 5")'
            ),
        )
        p_db.add_argument("--terse", action="store_true", help="Compact single-line JSON")

        # ---- extension subcommands (registered by plugins via canary_query_subcommand) ----
        canary.config.pluginmanager.hook.canary_query_subcommand(subparsers=sub)

    def execute(self, args: argparse.Namespace) -> int:
        """Dispatch to the first plugin that handles ``args.query_subcmd``."""
        result = canary.config.pluginmanager.hook.canary_query_execute(args=args)
        if result is not None:
            return result
        print(self.description)
        return 1


# ---------------------------------------------------------------------------
# Helpers (also used by canary_hpc and tests)
# ---------------------------------------------------------------------------


def _job_lockfile(workspace: Workspace, jobid: str) -> Path:
    """Resolve *jobid* to its ``testcase.lock`` path, raising if not found."""
    job = workspace.find_job(jobid)
    lockfile = job.lockfile
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    return lockfile


def _find_cache_path(workspace: Workspace, spec_id: str) -> Path | None:
    """Return the path to the per-job timing cache file, or None if absent."""
    from ..job import find_cache_dir

    cache_dir = find_cache_dir(start=workspace.root)
    if cache_dir is None:
        cache_dir = workspace.root / "cache"
    cache_file = cache_dir / "jobs" / spec_id[:2] / spec_id[2:]
    if cache_file.exists():
        return cache_file
    # Try legacy location
    legacy = workspace.root / "cache" / "cases" / spec_id[:2] / spec_id[2:]
    if legacy.exists():
        return legacy
    return None


def _resolve_session_dir(workspace: Workspace, session: str) -> Path:
    """Resolve a session name, prefix, or ``"latest"`` to its directory path."""
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


def _db_results_for_session(workspace: Workspace, session_name: str) -> list[dict[str, Any]]:
    """Return all result rows for a given session from the workspace DB."""
    rows = workspace.db.connection.execute(
        "SELECT * FROM results WHERE session = ? ORDER BY spec_name", (session_name,)
    ).fetchall()
    return [workspace.db._reconstruct_results(row) for row in rows]


def _db_outcome_counts_for_session(workspace: Workspace, session_name: str) -> dict[str, int]:
    """Return {outcome_name: count} for all jobs in a session."""
    from ..status import Outcome

    rows = workspace.db.connection.execute(
        "SELECT status_outcome, COUNT(*) FROM results WHERE session = ? GROUP BY status_outcome",
        (session_name,),
    ).fetchall()
    result: dict[str, int] = {}
    for raw_outcome, count in rows:
        try:
            name = Outcome.factory(raw_outcome).name
        except (ValueError, KeyError):
            name = str(raw_outcome)
        result[name] = count
    return result


def _clean(data: Any) -> Any:
    """Recursively strip __type__ wrappers and normalise legacy enum dicts.

    Converts:
    - ``{"__type__": "...", "value": X}``  →  ``X``
    - Removes ``__type__`` keys from all other dicts
    """
    if isinstance(data, dict):
        # Legacy enum envelope: {"__type__": "...", "value": X}
        if "__type__" in data and set(data.keys()) <= {"__type__", "value"}:
            return _clean(data["value"])
        # Strip __type__ from general dicts and recurse
        return {k: _clean(v) for k, v in data.items() if k != "__type__"}
    elif isinstance(data, list):
        return [_clean(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# --where predicate parser
# ---------------------------------------------------------------------------

_WHERE_RE = re.compile(
    r"^(?P<path>[A-Za-z_][A-Za-z0-9_.]*)\s*(?P<op>==|!=|>=|<=|>|<)\s*(?P<value>.+)$"
)


def _parse_where(expr: str) -> Any:
    """Parse a --where expression and return a predicate callable.

    Supported syntax:  ``key.path OP value``
    where OP is one of  ==  !=  >  <  >=  <=
    and value is treated as a string (case-insensitive for status fields).
    """
    m = _WHERE_RE.match(expr.strip())
    if not m:
        raise ValueError(
            f"Invalid --where expression {expr!r}. "
            "Expected format: key.path==value  (e.g. status.outcome==FAILED)"
        )
    path = m.group("path")
    op = m.group("op")
    raw_value = m.group("value").strip()

    def _get(obj: Any, dotpath: str) -> Any:
        for part in dotpath.split("."):
            if not isinstance(obj, dict):
                return None
            obj = obj.get(part)
        return obj

    def _coerce(actual: Any, expected: str) -> tuple[Any, Any]:
        """Try to coerce expected to the same type as actual for comparison."""
        if isinstance(actual, (int, float)):
            try:
                return actual, type(actual)(expected)
            except (ValueError, TypeError):
                pass
        # Fall back to string comparison (case-insensitive for outcomes/categories)
        return str(actual).upper(), expected.upper()

    def predicate(obj: dict[str, Any]) -> bool:
        actual = _get(obj, path)
        a, b = _coerce(actual, raw_value)
        if op == "==":
            return a == b
        elif op == "!=":
            return a != b
        elif op == ">":
            return a > b  # type: ignore[operator]
        elif op == "<":
            return a < b  # type: ignore[operator]
        elif op == ">=":
            return a >= b  # type: ignore[operator]
        elif op == "<=":
            return a <= b  # type: ignore[operator]
        return False

    return predicate


# ---------------------------------------------------------------------------
# Built-in canary_query_execute implementations
# (registered in _canary.hooks with @hookimpl trylast=True)
# ---------------------------------------------------------------------------
# The implementations live in _canary/hooks.py so that they follow the
# established pattern for built-in hook implementations and canary_query_execute
# is a fully open extension point with no special-casing in Query.execute.


def _exec_job(args: argparse.Namespace) -> int:
    """Query a single job's ``testcase.lock`` or its timing cache."""
    workspace = Workspace.load()

    if args.cache:
        job = workspace.find_job(args.jobid)
        cache_path = _find_cache_path(workspace, job.id)
        if cache_path is None:
            sys.stderr.write(f"No cache entry found for job {args.jobid!r}\n")
            return 1
        data = json.loads(cache_path.read_text())
        print_json(data, terse=args.terse)
        return 0

    lockfile = _job_lockfile(workspace, args.jobid)
    data = json.loads(lockfile.read_text())

    if args.list_keys:
        print_query_paths(list_json_object_paths(data, args.path))
        return 0

    result = query_json(data, args.path)
    if args.clean:
        result = _clean(result)
    print_json(result, terse=args.terse)
    return 0


def _exec_session(args: argparse.Namespace) -> int:
    """Query a session lock file or expand its jobs into result rows."""
    workspace = Workspace.load()
    session_dir = _resolve_session_dir(workspace, args.session)

    if args.expand_jobs:
        return _exec_session_expand(workspace, session_dir, args)

    lockfile = session_dir / "session.lock"
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    data = json.loads(lockfile.read_text())

    if args.list_keys:
        print_query_paths(list_json_object_paths(data, args.path))
        return 0

    result = query_json(data, args.path)
    if args.clean:
        result = _clean(result)
    print_json(result, terse=args.terse)
    return 0


def _exec_session_expand(workspace: Workspace, session_dir: Path, args: argparse.Namespace) -> int:
    """Join session job_ids to DB result rows and emit as a JSON array."""
    lockfile = session_dir / "session.lock"
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    session_data = json.loads(lockfile.read_text())
    session_name = session_data.get("name", session_dir.name)

    rows = _db_results_for_session(workspace, session_name)
    predicate = _parse_where(args.where) if args.where else None

    out: list[dict[str, Any]] = []
    for row in rows:
        tk = row["timekeeper"]
        submitted = tk.get("_submitted", -1) if isinstance(tk, dict) else -1
        staged = tk.get("_staged", -1) if isinstance(tk, dict) else -1
        started = tk.get("_started", -1) if isinstance(tk, dict) else -1
        stopped = tk.get("_stopped", -1) if isinstance(tk, dict) else -1
        finished = tk.get("_finished", -1) if isinstance(tk, dict) else -1

        def elapsed(a: float, b: float) -> float:
            return round(b - a, 6) if a > 0 and b > 0 else -1.0

        entry: dict[str, Any] = {
            "id": row["id"],
            "name": row["spec_name"],
            "fullname": row["spec_fullname"],
            "file_path": row.get("file_path", ""),
            "exec_dir": str(workspace.sessions_dir / row["session"] / row["workspace"]),
            "session": row["session"],
            "exit_code": row["status"].code,
            "status": {
                "category": row["status"].category.value,
                "outcome": row["status"].outcome.name,
                "reason": row["status"].reason,
            },
            "timings": {
                "pending": elapsed(submitted, staged),
                "setup": elapsed(staged, started),
                "running": elapsed(started, stopped),
                "teardown": elapsed(stopped, finished),
                "total": elapsed(submitted, finished),
            },
        }

        if predicate and not predicate(entry):
            continue
        out.append(entry)

    print_json(out, terse=args.terse)
    return 0


def _exec_sessions(args: argparse.Namespace) -> int:
    """List all sessions with per-outcome job counts as a JSON array."""
    workspace = Workspace.load()
    sessions_dir = workspace.sessions_dir
    predicate = _parse_where(args.where) if args.where else None

    out: list[dict[str, Any]] = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        lockfile = session_dir / "session.lock"
        if not lockfile.exists():
            continue
        session_data = json.loads(lockfile.read_text())
        session_name = session_data.get("name", session_dir.name)

        counts = _db_outcome_counts_for_session(workspace, session_name)
        total = sum(counts.values())

        entry: dict[str, Any] = {
            "name": session_name,
            "started_on": session_data.get("started_on"),
            "finished_on": session_data.get("finished_on"),
            "returncode": session_data.get("returncode"),
            "argv": session_data.get("argv", []),
            "job_count": total,
            "outcomes": counts,
        }

        if predicate and not predicate(entry):
            continue
        out.append(entry)

    print_json(out, terse=args.terse)
    return 0


def _exec_db(args: argparse.Namespace) -> int:
    """Dispatch to ``schema``, ``stats``, or an arbitrary SQL SELECT statement."""
    workspace = Workspace.load()
    db_args: list[str] = args.db_args or []

    if not db_args:
        sys.stderr.write("canary query db: expected 'schema', 'stats', or a SQL SELECT statement\n")
        return 1

    keyword = db_args[0].lower().strip()

    if keyword == "schema":
        con = sqlite3.connect(workspace.db.path)
        rows = con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        con.close()
        out = {name: ddl for name, ddl in rows}
        print_json(out, terse=args.terse)
        return 0

    if keyword == "stats":
        con = sqlite3.connect(workspace.db.path)
        total = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        outcome_rows = con.execute(
            "SELECT status_outcome, COUNT(*) FROM results "
            "WHERE session = (SELECT MAX(session) FROM results AS r2 WHERE r2.spec_id = results.spec_id) "
            "GROUP BY status_outcome ORDER BY COUNT(*) DESC"
        ).fetchall()
        session_count = con.execute("SELECT COUNT(DISTINCT session) FROM results").fetchone()[0]
        latest = con.execute("SELECT MAX(session) FROM results").fetchone()[0]
        spec_count = con.execute("SELECT COUNT(*) FROM specs").fetchone()[0]
        con.close()
        outcomes = {outcome: count for outcome, count in outcome_rows}
        out_stats = {
            "spec_count": spec_count,
            "result_count": total,
            "session_count": session_count,
            "latest_session": latest,
            "outcomes": outcomes,
        }
        print_json(out_stats, terse=args.terse)
        return 0

    # Arbitrary SELECT
    sql = " ".join(db_args)
    sql_stripped = sql.strip().lower()
    if not sql_stripped.startswith("select"):
        sys.stderr.write("canary query db: only SELECT statements are permitted\n")
        return 1

    con = sqlite3.connect(workspace.db.path)
    con.row_factory = sqlite3.Row
    try:
        rows_sql = con.execute(sql).fetchall()
    except sqlite3.Error as e:
        sys.stderr.write(f"canary query db: SQL error: {e}\n")
        con.close()
        return 1
    con.close()

    out_sql = [dict(row) for row in rows_sql]
    print_json(out_sql, terse=args.terse)
    return 0
