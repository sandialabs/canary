# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""canary query — structured workspace inspection.

Subcommands
-----------
job <ID> [path]          Query a single job's testcase.lock
job <ID> env             Show the runtime environment snapshot (env.json)
job <ID> env.KEY         Show a single environment variable (e.g. env.CUDA_VISIBLE_DEVICES)
job <ID> --cache         Show per-job timing cache statistics
job <ID> --all-runs      Show all historical runs across sessions (oldest first)
session <S> [path]       Query a session's session.lock
session <S> --expand-jobs  Join session job_ids to DB result rows
session <S> --digest     One-line-per-job summary: name CATEGORY (implies --expand-jobs)
session <S> --watch[=N]  Poll and re-render every N seconds until all jobs are terminal
sessions                 List all sessions with summary statistics
jobs                     List all jobs — latest run per job across all sessions by default
jobs --session S         Scope to a single session (same data as session --expand-jobs)
jobs --watch[=N]         Poll and re-render every N seconds until all jobs are terminal
db schema                Emit workspace database DDL as JSON
db stats                 Emit per-outcome counts and session summary
db "<SQL>"               Execute a read-only SQL query, return JSON rows

The built-in subcommands (job, session, sessions, jobs, db) are implemented as
``@hookimpl(trylast=True, specname="canary_query_execute")`` functions in
``_canary.plugins.hooks``.  Extension subcommands are registered via the
``canary_query_subcommand`` hook and dispatched via ``canary_query_execute``.

Common flags
------------

.. code-block:: text

   --clean     Strip __type__ wrappers and normalise enum values to strings
   --terse     Compact single-line JSON output
   --list      List immediate child keys at the selected query path
   --digest    One-line-per-job compact summary (session and jobs subcommands)
   --where     Filter predicate for --expand-jobs / sessions / jobs / batches
               String fields:  status.outcome==FAILED  status.category==PASS
               Numeric fields: timings.queue_wait>3600  timings.running<60
               Operators: == != > < >= <=  (None fields: ordered ops -> False, != -> True)
   --watch     Poll and re-render the query every N seconds (default 10).  Exits
               automatically when every job in the selection has reached a terminal
               status category (i.e. not NONE).  Ctrl-C exits cleanly with code 0.
               In --terse mode emits one NDJSON document per cycle.

Agent shortcuts:

.. code-block:: text

   -c QUERY     Shortcut for ``canary learn capabilities QUERY``
   --skills Q   Shortcut for ``canary learn skills Q``
   -j JOB [P]   Shortcut for ``canary query job JOB [P]``
   -s SES [P]   Shortcut for ``canary query session SES [P]``
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import canary

from ..app.failure_analysis import collect_failure_groups
from ..app.failure_analysis import failure_signature_for_row
from ..app.failure_analysis import job_from_result_row
from ..app.failure_analysis import list_existing_logs
from ..app.failure_analysis import tail_lines
from ..app.paths import remap_path
from ..plugins.hookspec import hookimpl
from ..session.workspace import Session
from ..session.workspace import Workspace
from ..util.query_data import list_json_object_paths
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
from ..util.query_data import query_json
from .base import CanarySubcommand
from .learn import execute_capabilities_query
from .learn import execute_skills_query

if TYPE_CHECKING:
    from ..config.argparsing import Parser
    from ..core.job import Job


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
    """Structured inspection of Canary workspace data via job, session, sessions, jobs, compare, failures, and db subcommands."""

    name = "query"
    description = (
        "Query Canary workspace data.\n\n"
        "Agent shortcuts: -c QUERY, --skills QUERY, -j JOBID [PATH], -s SESSION [PATH]\n\n"
        "Subcommands: job, session, sessions, jobs, compare, failures, db\n\n"
        "Examples:\n"
        "  canary query -c overview\n"
        "  canary query --skills core.canary-orientation\n"
        "  canary query -j abc1234 measurements.data\n"
        "  canary query -s latest measurements\n"
        "  canary query job abc1234\n"
        "  canary query job abc1234 status.outcome\n"
        "  canary query job abc1234 env\n"
        "  canary query job abc1234 env.CUDA_VISIBLE_DEVICES\n"
        "  canary query job abc1234 --cache\n"
        "  canary query job abc1234 --all-runs\n"
        "  canary query session latest --expand-jobs\n"
        "  canary query session latest --expand-jobs --where status.outcome==FAILED\n"
        "  canary query session latest --digest\n"
        "  canary query session latest --digest --where status.category==PASS\n"
        "  canary query session latest --expand-jobs --watch\n"
        "  canary query session latest --expand-jobs --watch=30\n"
        "  canary query jobs\n"
        "  canary query jobs --where status.category==FAIL\n"
        "  canary query jobs --where timings.running>60\n"
        "  canary query jobs --session latest\n"
        "  canary query jobs --digest\n"
        "  canary query jobs --watch\n"
        "  canary query sessions\n"
        "  canary query db stats\n"
        "  canary query db schema\n"
        '  canary query db "SELECT spec_name, status_outcome FROM results LIMIT 10"\n'
    )

    def setup_parser(self, parser: "Parser") -> None:
        """Register built-in and extension subparsers under ``canary query``."""
        parser.add_argument(
            "-c",
            "--capabilities",
            dest="capabilities_query",
            metavar="QUERY",
            help="Shortcut for 'canary learn capabilities QUERY'",
        )
        parser.add_argument(
            "-k",
            "--skills",
            dest="skills_query",
            metavar="QUERY",
            help="Shortcut for 'canary learn skills QUERY'",
        )
        parser.add_argument(
            "-j",
            "--job",
            dest="job_shortcut",
            nargs="+",
            metavar="ARG",
            help="Shortcut for 'canary query job JOBID [PATH]'",
        )
        parser.add_argument(
            "-s",
            "--session",
            dest="session_shortcut",
            nargs="+",
            metavar="ARG",
            help="Shortcut for 'canary query session SESSION [PATH]'",
        )
        parser.add_argument("--clean", action="store_true", help="Strip __type__ wrappers")
        parser.add_argument("--terse", action="store_true", help="Compact single-line JSON")
        parser.add_argument(
            "--list",
            dest="list_keys",
            action="store_true",
            help="List queryable child keys at the selected path",
        )
        sub = parser.add_subparsers(dest="query_subcmd", metavar="SUBCMD")

        # ---- job ----
        p_job = sub.add_parser("job", help="Query a job's testcase.lock")
        p_job.add_argument("jobid", metavar="JOBID", help="Job ID (prefix or full 64-char)")
        p_job.add_argument(
            "path",
            nargs="?",
            default=".",
            help=(
                "JSON path expression (default: whole document). "
                "Use 'env' or 'env.KEY' to query the runtime environment snapshot "
                "(e.g. 'env.CUDA_VISIBLE_DEVICES')."
            ),
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
        p_job.add_argument(
            "--all-runs",
            action="store_true",
            help=(
                "Show all historical runs of this job across all sessions "
                "(oldest first), each with session, exit_code, status, and timings. "
                "Useful for retried or re-run jobs. "
                "Note: runs across code rebuilds may not represent the same computation."
            ),
        )
        p_job.add_argument(
            "--blockers",
            action="store_true",
            help="Explain which dependency failures blocked this job from running",
        )
        p_job.add_argument(
            "--recursive",
            action="store_true",
            help="When used with --blockers, include transitive upstream dependencies",
        )
        p_job.add_argument(
            "--signatures",
            action="store_true",
            help="When used with --blockers, include grouped root failure signatures",
        )
        p_job.add_argument(
            "--missing-inputs",
            action="store_true",
            help="Summarize missing staged inputs for this job",
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
            "--digest",
            action="store_true",
            help=(
                "Print a compact one-line-per-job summary: name CATEGORY "
                "(e.g. TJO=1800 PASS).  Implies --expand-jobs.  "
                "Combine with --where to filter."
            ),
        )
        p_ses.add_argument(
            "--list",
            dest="list_keys",
            action="store_true",
            help="List queryable child keys at the selected path",
        )
        p_ses.add_argument(
            "--watch",
            nargs="?",
            const=10,
            default=None,
            type=float,
            metavar="SECONDS",
            help=(
                "Poll and re-render every SECONDS (default 10). "
                "Implies --expand-jobs. "
                "Exits automatically when every job has reached a terminal status. "
                "Ctrl-C exits cleanly with code 0. "
                "With --terse, emits one NDJSON document per cycle."
            ),
        )
        p_ses.add_argument(
            "--with",
            dest="with_fields",
            action="append",
            default=None,
            metavar="FIELD",
            help="Augment expanded job rows with extra projections, e.g. logs or logs:40",
        )
        p_ses.add_argument(
            "--missing-inputs",
            action="store_true",
            help="Summarize missing staged inputs across the session",
        )

        # ---- sessions ----
        p_sessions = sub.add_parser("sessions", help="List all sessions with summary statistics")
        p_sessions.add_argument(
            "--where", metavar="EXPR", help='Filter predicate, e.g. "returncode==0"'
        )
        p_sessions.add_argument("--terse", action="store_true", help="Compact single-line JSON")

        # ---- jobs ----
        p_jobs = sub.add_parser(
            "jobs",
            help=(
                "List jobs across all sessions — latest run per job by default; "
                "use --session to scope to one session"
            ),
        )
        p_jobs.add_argument(
            "--session",
            metavar="SESSION",
            default=None,
            help=(
                'Session name, prefix, or "latest".  '
                "Default: latest run per job across ALL sessions "
                "(each record includes a session provenance field)"
            ),
        )
        p_jobs.add_argument(
            "--where",
            metavar="EXPR",
            help=(
                "Filter predicate, e.g. "
                '"status.outcome==FAILED", "status.category==FAIL", '
                '"timings.running>60"'
            ),
        )
        p_jobs.add_argument("--terse", action="store_true", help="Compact single-line JSON")
        p_jobs.add_argument(
            "--digest",
            action="store_true",
            help="Print a compact one-line-per-job summary: name CATEGORY",
        )
        p_jobs.add_argument(
            "--watch",
            nargs="?",
            const=10,
            default=None,
            type=float,
            metavar="SECONDS",
            help=(
                "Poll and re-render every SECONDS (default 10). "
                "Exits automatically when every job has reached a terminal status. "
                "Ctrl-C exits cleanly with code 0. "
                "With --terse, emits one NDJSON document per cycle."
            ),
        )
        p_jobs.add_argument(
            "--with",
            dest="with_fields",
            action="append",
            default=None,
            metavar="FIELD",
            help="Augment rows with extra projections, e.g. logs or logs:40",
        )

        # ---- compare ----
        p_compare = sub.add_parser("compare", help="Compare two sessions job-by-job")
        p_compare.add_argument("base_session", metavar="BASE_SESSION", help="Baseline session")
        p_compare.add_argument(
            "new_session", nargs="?", default="latest", metavar="NEW_SESSION", help="New session"
        )
        p_compare.add_argument("--where", metavar="EXPR", help="Optional compare-row predicate")
        p_compare.add_argument(
            "--by",
            choices=("spec_id", "name"),
            default="spec_id",
            help="How to match jobs between sessions",
        )
        p_compare.add_argument(
            "--signatures",
            action="store_true",
            help="Include failure signatures for new and still-failing jobs",
        )
        p_compare.add_argument(
            "--digest", action="store_true", help="Print one line per compared job instead of JSON"
        )
        p_compare.add_argument("--terse", action="store_true", help="Compact single-line JSON")

        # ---- failures ----
        p_failures = sub.add_parser("failures", help="Group failures by normalized log signature")
        p_failures.add_argument(
            "--session",
            metavar="SESSION",
            default="latest",
            help='Session name, prefix, or "latest"',
        )
        p_failures.add_argument("--where", metavar="EXPR", help="Optional job filter predicate")
        p_failures.add_argument(
            "--group-by",
            choices=("signature", "exception", "frame", "reason", "file_path"),
            default="signature",
            help="Grouping key for failure buckets",
        )
        p_failures.add_argument(
            "--frame-filter",
            metavar="REGEX",
            default=None,
            help="Regex used to choose the most relevant traceback frame",
        )
        p_failures.add_argument(
            "--log",
            action="append",
            default=None,
            dest="log_names",
            metavar="FILE",
            help="Workspace log file to scan; may be passed more than once",
        )
        p_failures.add_argument(
            "--include-pass-with-errors",
            action="store_true",
            help="Also include PASS jobs whose logs contain a traceback or command error",
        )
        p_failures.add_argument("--terse", action="store_true", help="Compact single-line JSON")

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
        shortcut = _query_shortcut_mode(args)
        if shortcut is not None:
            return shortcut
        result = canary.config.pluginmanager.hook.canary_query_execute(args=args)
        if result is not None:
            return result
        print(self.description)
        return 1


def _query_shortcut_mode(args: argparse.Namespace) -> int | None:
    shortcuts = {
        "capabilities": getattr(args, "capabilities_query", None),
        "skills": getattr(args, "skills_query", None),
        "job": getattr(args, "job_shortcut", None),
        "session": getattr(args, "session_shortcut", None),
    }
    active = [name for name, value in shortcuts.items() if value is not None]

    if not active:
        return None

    if len(active) > 1:
        sys.stderr.write(
            "canary query: choose only one shortcut mode from -c/--capabilities, "
            "-k/--skills, -j/--job, or -s/--session\n"
        )
        return 2

    if getattr(args, "query_subcmd", None) is not None:
        sys.stderr.write("canary query: shortcut options cannot be combined with subcommands\n")
        return 2

    if active[0] == "capabilities":
        return execute_capabilities_query(
            args.capabilities_query,
            terse=getattr(args, "terse", False),
            list_keys=getattr(args, "list_keys", False),
        )

    if active[0] == "skills":
        return execute_skills_query(
            args.skills_query,
            terse=getattr(args, "terse", False),
            list_keys=getattr(args, "list_keys", False),
        )

    if active[0] == "job":
        shortcut_args = _parse_shortcut_target(args.job_shortcut, "job")
        if shortcut_args is None:
            return 2
        jobid, path = shortcut_args
        return _exec_job(
            argparse.Namespace(
                jobid=jobid,
                path=path,
                cache=False,
                all_runs=False,
                blockers=False,
                recursive=False,
                signatures=False,
                missing_inputs=False,
                clean=getattr(args, "clean", False),
                terse=getattr(args, "terse", False),
                list_keys=getattr(args, "list_keys", False),
            )
        )

    shortcut_args = _parse_shortcut_target(args.session_shortcut, "session")
    if shortcut_args is None:
        return 2
    session, path = shortcut_args
    return _exec_session(
        argparse.Namespace(
            session=session,
            path=path,
            expand_jobs=False,
            digest=False,
            where=None,
            clean=getattr(args, "clean", False),
            terse=getattr(args, "terse", False),
            list_keys=getattr(args, "list_keys", False),
            watch=None,
            with_fields=None,
            missing_inputs=False,
        )
    )


def _parse_shortcut_target(values: list[str], kind: str) -> tuple[str, str] | None:
    if len(values) > 2:
        sys.stderr.write(
            f"canary query: shortcut '-{kind[0]}' expects {kind.upper()} [PATH], got: {' '.join(values)}\n"
        )
        return None
    target = values[0]
    path = values[1] if len(values) == 2 else "."
    return target, path


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


def _find_cache_path(job: "Job") -> Path | None:
    """Return the path to the per-job timing cache file, or None if absent."""
    from ..history.store import HistoryStore

    store = HistoryStore.open(start=job.workspace.root)
    return store.path_for(job)


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
    return workspace.db.get_results_for_session(session_name)


def _db_outcome_counts_for_session(workspace: Workspace, session_name: str) -> dict[str, int]:
    """Return {outcome_name: count} for all jobs in a session."""
    from ..core.status import Outcome

    result: dict[str, int] = {}
    for raw_outcome, count in workspace.db.get_outcome_counts_for_session(session_name).items():
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
    Numeric fields (int/float) are compared numerically so that expressions
    like ``timings.queue_wait>3600`` work correctly.  If the actual field
    value is ``None`` (e.g. a batch whose timing has not yet been recorded),
    ordered comparisons (``>  <  >=  <=``) return ``False``; equality (``==``)
    also returns ``False`` while ``!=`` returns ``True``.
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

    def _coerce(actual: Any, expected: str) -> tuple[Any, Any] | None:
        """Try to coerce expected to the same type as actual for comparison.

        Returns None when actual is None (caller should handle the null case).
        """
        if actual is None:
            return None
        if isinstance(actual, (int, float)):
            try:
                return actual, type(actual)(expected)
            except (ValueError, TypeError):
                pass
        # Fall back to string comparison (case-insensitive for outcomes/categories)
        return str(actual).upper(), expected.upper()

    def predicate(obj: dict[str, Any]) -> bool:
        actual = _get(obj, path)
        coerced = _coerce(actual, raw_value)
        if coerced is None:
            # actual is None — ordered comparisons are False; != is True
            return op == "!="
        a, b = coerced
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
# (registered in _canary.plugins.hooks with @hookimpl trylast=True)
# ---------------------------------------------------------------------------
# The implementations live in _canary/hooks.py so that they follow the
# established pattern for built-in hook implementations and canary_query_execute
# is a fully open extension point with no special-casing in Query.execute.


def _exec_job(args: argparse.Namespace) -> int:
    """Query a single job's ``testcase.lock``, timing cache, or run history."""
    workspace = Workspace.load()

    if getattr(args, "blockers", False):
        info = _job_blockers(
            workspace,
            args.jobid,
            recursive=getattr(args, "recursive", False),
            signatures=getattr(args, "signatures", False),
        )
        print_json(info, terse=args.terse)
        return 0

    if getattr(args, "missing_inputs", False):
        lockfile = _job_lockfile(workspace, args.jobid)
        data = json.loads(lockfile.read_text())
        inputs = data.get("measurements", {}).get("data", {}).get("inputs", [])
        missing = [item for item in inputs if not item.get("exists_now")]
        print_json(missing, terse=args.terse)
        return 0

    if getattr(args, "all_runs", False):
        job = workspace.find_job(args.jobid)
        workspace.db.connect()
        try:
            history = workspace.db.get_result_history(job.id)
        finally:
            workspace.db.close()
        if not history:
            sys.stderr.write(f"No run history found for job {args.jobid!r}\n")
            return 1
        out: list[dict[str, Any]] = [_row_to_job_entry(workspace, row) for row in history]
        print_json(out, terse=args.terse)
        return 0

    if args.cache:
        job = workspace.find_job(args.jobid)
        cache_path = _find_cache_path(job)
        if cache_path is None:
            sys.stderr.write(f"No cache entry found for job {args.jobid!r}\n")
            return 1
        data = json.loads(cache_path.read_text())
        print_json(data, terse=args.terse)
        return 0

    lockfile = _job_lockfile(workspace, args.jobid)
    data = json.loads(lockfile.read_text())

    # Merge env.json as a top-level "env" key so that path expressions like
    # "env" and "env.CUDA_VISIBLE_DEVICES" work identically to "measurements"
    # and "measurements.flux".  The file is loaded lazily — only when the
    # query path starts with "env" — so queries that don't touch env pay no
    # filesystem cost.
    path = args.path.lstrip(".")
    if path == "env" or path.startswith("env.") or path.startswith("env["):
        env_file = lockfile.parent / "env.json"
        if env_file.exists():
            data["env"] = json.loads(env_file.read_text())
        else:
            sys.stderr.write(
                f"No env.json found for job {args.jobid!r} (file not present at {env_file})\n"
            )
            return 1

    if args.list_keys:
        print_query_paths(list_json_object_paths(data, args.path))
        return 0

    result = query_json(data, args.path)
    if args.clean:
        result = _clean(result)
    print_json(result, terse=args.terse)
    return 0


def _job_blockers(
    workspace: Workspace, jobid: str, *, recursive: bool = False, signatures: bool = False
) -> dict[str, Any]:
    job = workspace.find_job(jobid)
    seed_ids = {job.id}
    dep_ids = (
        workspace.db.get_upstream_ids(seed_ids)
        if recursive
        else set(dep.job.id for dep in job.dependencies)
    )
    if not dep_ids:
        return {
            "id": job.id,
            "name": job.name,
            "outcome": job.status.outcome.name,
            "blocked_by": {"total_deps": 0, "failed": 0, "passed": 0, "root_signatures": []},
        }

    dep_rows = workspace.db.get_results(list(dep_ids))
    failed_rows = [row for row in dep_rows.values() if row["status"].category.value == "FAIL"]
    passed_rows = [row for row in dep_rows.values() if row["status"].category.value == "PASS"]
    root_signatures: list[dict[str, Any]] = []
    if signatures:
        grouped = collect_failure_groups(workspace, failed_rows)
        root_signatures = [
            {"signature": group["signature_normalized"], "count": group["count"]}
            for group in grouped
        ]

    return {
        "id": job.id,
        "name": job.name,
        "outcome": job.status.outcome.name,
        "blocked_by": {
            "total_deps": len(dep_ids),
            "failed": len(failed_rows),
            "passed": len(passed_rows),
            "root_signatures": root_signatures,
        },
    }


def _exec_session(args: argparse.Namespace) -> int:
    """Query a session lock file or expand its jobs into result rows."""
    workspace = Workspace.load()
    session_dir = _resolve_session_dir(workspace, args.session)

    if (
        args.expand_jobs
        or getattr(args, "digest", False)
        or getattr(args, "watch", None) is not None
    ):
        return _exec_session_expand(workspace, session_dir, args)

    lockfile = session_dir / "session.lock"
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    data = json.loads(lockfile.read_text())

    if args.list_keys:
        print_query_paths(list_json_object_paths(data, args.path))
        return 0

    result = query_json(data, args.path)
    if getattr(args, "missing_inputs", False):
        session_name = data.get("name", session_dir.name)
        rows = _db_results_for_session(workspace, session_name)
        missing = []
        for row in rows:
            job = workspace.find_job(row["id"])
            lock_data = json.loads(job.lockfile.read_text())
            inputs = lock_data.get("measurements", {}).get("data", {}).get("inputs", [])
            missing.extend(item for item in inputs if not item.get("exists_now"))
        result = missing
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
    predicate = _parse_where(args.where) if args.where else None
    digest = getattr(args, "digest", False)
    watch_interval = getattr(args, "watch", None)

    def _fetch() -> tuple[list[dict[str, Any]], int]:
        rows = _db_results_for_session(workspace, session_name)
        out: list[dict[str, Any]] = []
        for row in rows:
            entry = _row_to_job_entry(workspace, row)
            _apply_with_fields(
                workspace, row, entry, getattr(args, "with_fields", None) or ["logs"]
            )
            if predicate and not predicate(entry):
                continue
            out.append(entry)
        return out, 0

    if watch_interval is not None:
        return _watch_loop(
            float(watch_interval), fetch=_fetch, terse=getattr(args, "terse", False), digest=digest
        )

    out, _ = _fetch()

    if digest:
        _emit_digest(out)
        return 0

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


def _batch_timings_for_job(workspace: Workspace, job_id: str, session: str) -> dict[str, float]:
    """Look up batch-level timings for a job whose own timekeeper is empty.

    Scans ``sessions/<session>/hpc.batches/*/batch.lock`` files for one whose
    ``jobs`` list contains *job_id*.  Returns a timings dict with keys
    ``pending``, ``setup``, ``running``, ``teardown``, ``total`` where
    available, defaulting to ``-1.0``.  Also includes ``_started_at`` and
    ``_stopped_at`` as absolute unix epoch floats (``-1.0`` when unavailable)
    so callers can use them for overlap/concurrency analysis without a second
    batch-lock scan.  All duration values are rounded to 6 decimal places.

    This is a best-effort fallback for HPC one-job-per-batch Slurm runs where
    the child job's timekeeper only gets coarse timestamps (the batch wall-clock
    start/stop), not the fine-grained phase breakdown recorded by local workers.
    Returns an all-``-1.0`` dict when no matching batch is found.
    """
    import json as _json

    empty: dict[str, float] = {
        "pending": -1.0,
        "setup": -1.0,
        "running": -1.0,
        "teardown": -1.0,
        "total": -1.0,
        "_started_at": -1.0,
        "_stopped_at": -1.0,
    }
    batches_dir = workspace.sessions_dir / session / "hpc.batches"
    if not batches_dir.is_dir():
        return empty

    for batch_lock in batches_dir.glob("*/batch.lock"):
        try:
            data = _json.loads(batch_lock.read_text())
        except (OSError, ValueError):  # nosec B112 — skip unreadable/malformed lock files
            continue
        if job_id not in data.get("jobs", []):
            continue
        # Found the owning batch — derive timings from its timekeeper.
        tk = data.get("timekeeper", {})
        if isinstance(tk, str):
            try:
                tk = _json.loads(tk)
            except ValueError:
                tk = {}
        b_submitted: float = float(tk.get("_submitted", -1) or -1)
        b_started: float = float(tk.get("_started", -1) or -1)
        b_stopped: float = float(tk.get("_stopped", -1) or -1)

        def _el(a: float, b: float) -> float:
            return round(b - a, 6) if a > 0 and b > 0 else -1.0

        return {
            # pending = queue wait (batch submitted → Slurm job started)
            "pending": _el(b_submitted, b_started),
            # setup = 0 for HPC (no staging separate from start)
            "setup": -1.0,
            # running = actual compute time (Slurm start → stop)
            "running": _el(b_started, b_stopped),
            # teardown not tracked separately at batch level
            "teardown": -1.0,
            # total = wall time from submission to completion
            "total": _el(b_submitted, b_stopped),
            # absolute epoch timestamps for overlap/concurrency analysis
            "_started_at": b_started if b_started > 0 else -1.0,
            "_stopped_at": b_stopped if b_stopped > 0 else -1.0,
        }
    return empty


def _batch_last_activity_for_job(workspace: Workspace, job_id: str, session: str) -> float | None:
    """Return the ``last_activity`` unix timestamp from the owning batch.lock.

    Scans ``sessions/<session>/hpc.batches/*/batch.lock`` files for one whose
    ``jobs`` list contains *job_id* and returns the ``last_activity`` field if
    present.  Returns ``None`` when no match is found or the field is absent
    (e.g. the batch has not started or was written by an older canary version).
    """
    import json as _json

    batches_dir = workspace.sessions_dir / session / "hpc.batches"
    if not batches_dir.is_dir():
        return None
    for batch_lock in batches_dir.glob("*/batch.lock"):
        try:
            data = _json.loads(batch_lock.read_text())
        except (OSError, ValueError):  # nosec B112 — skip unreadable/malformed lock files
            continue
        if job_id not in data.get("jobs", []):
            continue
        val = data.get("last_activity")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
        return None
    return None


def _row_to_job_entry(workspace: Workspace, row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB result row dict into the standard job entry format.

    Used by both ``_exec_session_expand`` and ``_exec_jobs`` to ensure a
    consistent record shape.

    Timings are derived from the job's own ``timekeeper`` when available.  For
    HPC one-job-per-batch Slurm runs the child job's per-phase timestamps are
    often ``-1.0`` (the fine-grained lifecycle is tracked at the batch level).
    In that case the function falls back to scanning the owning
    ``batch.lock`` and mapping the batch-level wall-clock phases to the
    standard timing keys (``pending`` = queue wait, ``running`` = compute
    wall-clock, ``total`` = submission-to-completion).

    ``started_at`` and ``stopped_at`` are absolute unix epoch floats marking
    when the job's actual execution began and ended.  For local-worker jobs
    these come from ``timekeeper._started`` / ``timekeeper._stopped``.  For
    HPC batch jobs they fall back to the batch-level Slurm start/stop times.
    Both are ``null`` when no timestamp is available.  These fields enable
    overlap/concurrency analysis without reading raw lock files.

    The ``last_activity`` field is a unix epoch float recording the most recent
    time the owning batch's output file was written to.  It is populated from
    the ``last_activity`` key in the owning ``batch.lock`` (written by the
    ``batchexec`` polling loop) and is ``null`` for local-worker jobs or when
    the batch has not yet started writing output.  Callers should treat it as
    an I/O liveness signal, NOT as a measure of application progress.
    """
    tk = row["timekeeper"]

    def _tk_get(key: str) -> float:
        """Extract a timekeeper field whether tk is a dict or a Timekeeper object."""
        if isinstance(tk, dict):
            return float(tk.get(key, -1) or -1)
        return float(getattr(tk, key, -1) or -1)

    submitted = _tk_get("_submitted")
    staged = _tk_get("_staged")
    started = _tk_get("_started")
    stopped = _tk_get("_stopped")
    finished = _tk_get("_finished")

    def elapsed(a: float, b: float) -> float:
        return round(b - a, 6) if a > 0 and b > 0 else -1.0

    timings = {
        "pending": elapsed(submitted, staged),
        "setup": elapsed(staged, started),
        "running": elapsed(started, stopped),
        "teardown": elapsed(stopped, finished),
        "total": elapsed(submitted, finished),
    }

    # started_at / stopped_at from the job's own timekeeper (local workers).
    started_at: float | None = float(started) if started > 0 else None
    stopped_at: float | None = float(stopped) if stopped > 0 else None

    # Fall back to batch-level timings for HPC child jobs whose own timekeeper
    # has no meaningful phase data (all -1.0).  This is the common case for
    # one-job-per-batch Slurm runs where fine-grained lifecycle events are
    # tracked at the batch level, not the individual job level.
    if all(v < 0 for v in timings.values()):
        batch_timings = _batch_timings_for_job(workspace, row["id"], row["session"])
        timings = {k: v for k, v in batch_timings.items() if not k.startswith("_")}
        if started_at is None:
            b_started = batch_timings.get("_started_at", -1.0)
            started_at = float(b_started) if b_started > 0 else None
        if stopped_at is None:
            b_stopped = batch_timings.get("_stopped_at", -1.0)
            stopped_at = float(b_stopped) if b_stopped > 0 else None

    # last_activity: HPC batch I/O liveness signal from the owning batch.lock.
    # None for local-worker jobs (no batch) or when the batch has not started.
    last_activity = _batch_last_activity_for_job(workspace, row["id"], row["session"])

    session_dir = workspace.sessions_dir / row["session"]
    try:
        root_at_creation = Session.load_lock_data(session_dir).get("root_at_creation")
    except FileNotFoundError:
        root_at_creation = None

    return {
        "id": row["id"],
        "name": row["spec_name"],
        "fullname": row["spec_fullname"],
        "file_path": row.get("file_path", ""),
        "exec_dir": remap_path(
            session_dir / row["workspace"],
            root_at_creation=root_at_creation,
            current_root=workspace.root.parent,
        ),
        "session": row["session"],
        "exit_code": row["status"].code,
        "status": {
            "category": row["status"].category.value,
            "outcome": row["status"].outcome.name,
            "reason": row["status"].reason,
        },
        "timings": timings,
        "started_at": started_at,
        "stopped_at": stopped_at,
        "last_activity": last_activity,
    }


def _emit_digest(out: list[dict[str, Any]]) -> None:
    """Write one line per job entry: ``name CATEGORY``."""
    for entry in out:
        category = entry.get("status", {}).get("category", "UNKNOWN")
        sys.stdout.write(f"{entry['name']} {category}\n")


def _all_terminal(out: list[dict[str, Any]]) -> bool:
    """Return True when every job entry has a non-NONE status category."""
    for entry in out:
        cat = entry.get("status", {}).get("category", "NONE")
        if cat == "NONE" or cat is None:
            return False
    return bool(out)  # empty list → keep polling (nothing to watch yet)


def _watch_render(out: list[dict[str, Any]], *, terse: bool, digest: bool) -> None:
    """Render one cycle of --watch output to stdout."""
    if digest:
        _emit_digest(out)
    elif terse:
        # NDJSON: one compact JSON document per cycle
        print_json(out, terse=True)
    else:
        # Human mode: emit a separator header so successive renders are distinct
        now_str = time.strftime("%Y-%m-%dT%H:%M:%S")
        sys.stdout.write(f"--- {now_str} ---\n")
        print_json(out, terse=False)
    sys.stdout.flush()


def _watch_loop(interval: float, *, fetch: Any, terse: bool, digest: bool) -> int:
    """Drive the ``--watch`` poll loop.

    *fetch* is a zero-argument callable that returns ``(out, rc)`` where *out*
    is the current list of job-entry dicts and *rc* is the exit code to return
    if an error occurs.  The loop re-calls *fetch* every *interval* seconds.

    Terminal condition: every job in *out* has a non-NONE status category.
    The final render is always emitted before returning so the caller sees a
    clean terminal state.

    Returns 0 on success, non-zero if *fetch* returns an error rc.
    """
    try:
        while True:
            out, rc = fetch()
            if rc != 0:
                return rc
            _watch_render(out, terse=terse, digest=digest)
            if _all_terminal(out):
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        # Final render with current state, then exit cleanly
        try:
            out, _ = fetch()
            _watch_render(out, terse=terse, digest=digest)
        except Exception:  # nosec B110 — best-effort final render on Ctrl-C; errors are ignored
            pass
        sys.stdout.flush()
        return 0


def _exec_jobs(args: argparse.Namespace) -> int:
    """List jobs as a JSON array.

    Default behaviour (no ``--session``): returns the **latest run** of each
    distinct job (keyed by spec_id) across **all sessions**, with a ``session``
    provenance field on each record.

    With ``--session S``: scopes to that single session only, equivalent to
    ``canary query session S --expand-jobs``.
    """
    workspace = Workspace.load()
    predicate = _parse_where(args.where) if args.where else None
    session_arg = getattr(args, "session", None)
    digest = getattr(args, "digest", False)
    watch_interval = getattr(args, "watch", None)

    def _fetch() -> tuple[list[dict[str, Any]], int]:
        if session_arg is not None:
            session_dir = _resolve_session_dir(workspace, session_arg)
            rows = _db_results_for_session(workspace, session_dir.name)
        else:
            workspace.db.connect()
            try:
                result_map = workspace.db.get_results()
            finally:
                workspace.db.close()
            rows = list(result_map.values())
            rows.sort(key=lambda r: r.get("spec_name", ""))

        out: list[dict[str, Any]] = []
        for row in rows:
            entry = _row_to_job_entry(workspace, row)
            _apply_with_fields(
                workspace, row, entry, getattr(args, "with_fields", None) or ["logs"]
            )
            if predicate and not predicate(entry):
                continue
            out.append(entry)
        return out, 0

    if watch_interval is not None:
        return _watch_loop(
            float(watch_interval), fetch=_fetch, terse=getattr(args, "terse", False), digest=digest
        )

    out, _ = _fetch()

    if digest:
        _emit_digest(out)
        return 0

    print_json(out, terse=args.terse)
    return 0


def _exec_failures(args: argparse.Namespace) -> int:
    workspace = Workspace.load()
    session_dir = _resolve_session_dir(workspace, args.session)
    rows = _db_results_for_session(workspace, session_dir.name)
    predicate = _parse_where(args.where) if args.where else None
    if predicate is not None:
        rows = [row for row in rows if predicate(_row_to_job_entry(workspace, row))]
    groups = collect_failure_groups(
        workspace,
        rows,
        group_by=args.group_by,
        frame_filter=args.frame_filter,
        include_pass_with_errors=getattr(args, "include_pass_with_errors", False),
        log_names=getattr(args, "log_names", None),
    )
    print_json(groups, terse=args.terse)
    return 0


def _exec_compare(args: argparse.Namespace) -> int:
    workspace = Workspace.load()
    base_rows = _rows_for_named_session(workspace, args.base_session)
    new_rows = _rows_for_named_session(workspace, args.new_session)
    by_name = getattr(args, "by", "spec_id") == "name"
    include_signatures = getattr(args, "signatures", False)

    def key_for(row: dict[str, Any]) -> str:
        return row["spec_name"] if by_name else row["id"]

    base_map = {key_for(row): row for row in base_rows}
    new_map = {key_for(row): row for row in new_rows}
    all_keys = sorted(set(base_map) | set(new_map))
    predicate = _parse_where(args.where) if args.where else None

    result: dict[str, Any] = {
        "base": args.base_session,
        "new": args.new_session,
        "summary": {
            "fixed": 0,
            "new_failures": 0,
            "still_failing": 0,
            "still_failing_signature_changed": 0,
            "missing_in_new": 0,
            "new_jobs": 0,
        },
        "fixed": [],
        "new_failures": [],
        "still_failing": [],
        "missing_in_new": [],
        "new_jobs": [],
    }
    digest_rows: list[str] = []

    for key in all_keys:
        base_row = base_map.get(key)
        new_row = new_map.get(key)
        compare_row = _build_compare_row(
            workspace, base_row, new_row, include_signatures=include_signatures
        )
        if predicate and not predicate(compare_row):
            continue
        bucket = compare_row["kind"]
        if bucket == "fixed":
            result["summary"]["fixed"] += 1
            result["fixed"].append(compare_row)
        elif bucket == "new_failures":
            result["summary"]["new_failures"] += 1
            result["new_failures"].append(compare_row)
        elif bucket == "still_failing":
            result["summary"]["still_failing"] += 1
            if compare_row.get("signature_changed"):
                result["summary"]["still_failing_signature_changed"] += 1
            result["still_failing"].append(compare_row)
        elif bucket == "missing_in_new":
            result["summary"]["missing_in_new"] += 1
            result["missing_in_new"].append(compare_row)
        elif bucket == "new_jobs":
            result["summary"]["new_jobs"] += 1
            result["new_jobs"].append(compare_row)
        if getattr(args, "digest", False):
            digest_rows.append(_compare_digest(compare_row))

    if getattr(args, "digest", False):
        for line in digest_rows:
            sys.stdout.write(line + "\n")
        return 0

    print_json(result, terse=args.terse)
    return 0


def _rows_for_named_session(workspace: Workspace, session_name: str) -> list[dict[str, Any]]:
    session_dir = _resolve_session_dir(workspace, session_name)
    return _db_results_for_session(workspace, session_dir.name)


def _build_compare_row(
    workspace: Workspace,
    base_row: dict[str, Any] | None,
    new_row: dict[str, Any] | None,
    *,
    include_signatures: bool,
) -> dict[str, Any]:
    if base_row is None and new_row is None:
        raise ValueError("compare row requires at least one side")
    if base_row is None:
        assert new_row is not None
        new_entry = _row_to_job_entry(workspace, new_row)
        return {
            "kind": "new_jobs",
            "id": new_row["id"],
            "name": new_row["spec_name"],
            "base": None,
            "new": new_row["status"].outcome.name,
            "new_status": new_entry["status"],
        }
    if new_row is None:
        assert base_row is not None
        base_entry = _row_to_job_entry(workspace, base_row)
        return {
            "kind": "missing_in_new",
            "id": base_row["id"],
            "name": base_row["spec_name"],
            "base": base_row["status"].outcome.name,
            "new": None,
            "base_status": base_entry["status"],
        }

    assert base_row is not None
    assert new_row is not None
    base_entry = _row_to_job_entry(workspace, base_row)
    new_entry = _row_to_job_entry(workspace, new_row)
    base_nonpass = base_entry["status"]["category"] != "PASS"
    new_nonpass = new_entry["status"]["category"] != "PASS"
    compare_row: dict[str, Any] = {
        "id": new_row["id"],
        "name": new_row["spec_name"],
        "base": base_row["status"].outcome.name,
        "new": new_row["status"].outcome.name,
        "base_status": base_entry["status"],
        "new_status": new_entry["status"],
    }

    if base_nonpass and not new_nonpass:
        compare_row["kind"] = "fixed"
        return compare_row
    if not base_nonpass and new_nonpass:
        compare_row["kind"] = "new_failures"
        if include_signatures:
            signature = failure_signature_for_row(workspace, new_row)
            compare_row["signature"] = (
                None if signature is None else signature["signature_normalized"]
            )
        return compare_row
    if base_nonpass and new_nonpass:
        compare_row["kind"] = "still_failing"
        compare_row["signature_changed"] = False
        if include_signatures:
            base_signature = failure_signature_for_row(workspace, base_row)
            new_signature = failure_signature_for_row(workspace, new_row)
            compare_row["base_signature"] = (
                None if base_signature is None else base_signature["signature_normalized"]
            )
            compare_row["new_signature"] = (
                None if new_signature is None else new_signature["signature_normalized"]
            )
            compare_row["signature_changed"] = (
                compare_row["base_signature"] != compare_row["new_signature"]
            )
        return compare_row

    compare_row["kind"] = "unchanged_pass"
    return compare_row


def _compare_digest(compare_row: dict[str, Any]) -> str:
    base = compare_row.get("base") or "MISSING"
    new = compare_row.get("new") or "MISSING"
    suffix = " [sig changed]" if compare_row.get("signature_changed") else ""
    return f"{compare_row['name']} {base}->{new}{suffix}"


def _apply_with_fields(
    workspace: Workspace, row: dict[str, Any], entry: dict[str, Any], with_fields: list[str] | None
) -> None:
    if not with_fields:
        return
    requested = [field for field in with_fields if field and field.startswith("logs")]
    if not requested:
        return
    job = job_from_result_row(workspace, row)
    logs = list_existing_logs(job)
    tail_n = None
    for field in requested:
        _, _, suffix = field.partition(":")
        if suffix:
            tail_n = int(suffix)
            break
    if tail_n is not None:
        for item in logs:
            item["tail"] = tail_lines(Path(item["path"]), tail_n)
    entry["logs"] = logs


def _exec_db(args: argparse.Namespace) -> int:
    """Dispatch to ``schema``, ``stats``, or an arbitrary SQL SELECT statement."""
    workspace = Workspace.load()
    db_args: list[str] = args.db_args or []

    if not db_args:
        sys.stderr.write("canary query db: expected 'schema', 'stats', or a SQL SELECT statement\n")
        return 1

    keyword = db_args[0].lower().strip()

    if keyword == "schema":
        print_json(workspace.db.get_schema(), terse=args.terse)
        return 0

    if keyword == "stats":
        print_json(workspace.db.get_stats(), terse=args.terse)
        return 0

    # Arbitrary SELECT
    sql = " ".join(db_args)
    try:
        out_sql = workspace.db.select(sql)
    except ValueError:
        sys.stderr.write("canary query db: only SELECT statements are permitted\n")
        return 1
    except sqlite3.Error as e:
        sys.stderr.write(f"canary query db: SQL error: {e}\n")
        return 1

    print_json(out_sql, terse=args.terse)
    return 0
