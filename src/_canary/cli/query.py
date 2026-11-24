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
import sqlite3
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import canary

from ..app.failure_analysis import collect_failure_groups
from ..app.query_helpers import apply_with_fields
from ..app.query_helpers import build_compare_row
from ..app.query_helpers import clean
from ..app.query_helpers import compare_digest
from ..app.query_helpers import db_outcome_counts_for_session
from ..app.query_helpers import db_results_for_session
from ..app.query_helpers import find_cache_path
from ..app.query_helpers import job_blockers
from ..app.query_helpers import job_lockfile
from ..app.query_helpers import job_result_history
from ..app.query_helpers import parse_where
from ..app.query_helpers import resolve_session_dir as _resolve_session_dir
from ..app.query_helpers import row_to_job_entry
from ..app.query_helpers import rows_for_named_session
from ..plugins.hookspec import hookimpl
from ..util.query_data import list_json_object_paths
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
from ..util.query_data import query_json
from ..workspace.workspace import Workspace
from .base import CanarySubcommand
from .learn import execute_capabilities_query
from .learn import execute_skills_query

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
    """Structured inspection of Canary workspace data via job, session, sessions, jobs, compare, failures, and db subcommands."""

    name = "query"
    description = "Query workspace data"
    epilog = (
        "Agent shortcuts: -c QUERY, --skills QUERY, -j JOBID [PATH], -s SESSION [PATH]\n\n"
        "Subcommands: job, session, sessions, jobs, compare, failures, db\n\n"
        "Examples:\n\n"
        "[pad]canary query -c overview\n\n"
        "[pad]canary query --skills core.canary-orientation\n\n"
        "[pad]canary query -j abc1234 measurements.data\n\n"
        "[pad]canary query -s latest measurements\n\n"
        "[pad]canary query job abc1234\n\n"
        "[pad]canary query job abc1234 status.outcome\n\n"
        "[pad]canary query job abc1234 env\n\n"
        "[pad]canary query job abc1234 env.CUDA_VISIBLE_DEVICES\n\n"
        "[pad]canary query job abc1234 --cache\n\n"
        "[pad]canary query job abc1234 --all-runs\n\n"
        "[pad]canary query session latest --expand-jobs\n\n"
        "[pad]canary query session latest --expand-jobs --where status.outcome==FAILED\n\n"
        "[pad]canary query session latest --digest\n\n"
        "[pad]canary query session latest --digest --where status.category==PASS\n\n"
        "[pad]canary query session latest --expand-jobs --watch\n\n"
        "[pad]canary query session latest --expand-jobs --watch=30\n\n"
        "[pad]canary query jobs\n\n"
        "[pad]canary query jobs --where status.category==FAIL\n\n"
        "[pad]canary query jobs --where timings.running>60\n\n"
        "[pad]canary query jobs --session latest\n\n"
        "[pad]canary query jobs --digest\n\n"
        "[pad]canary query jobs --watch\n\n"
        "[pad]canary query sessions\n\n"
        "[pad]canary query db stats\n\n"
        "[pad]canary query db schema\n\n"
        '[pad]canary query db "SELECT spec_name, status_outcome FROM results LIMIT 10"'
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
        p_job.add_argument(
            "--session",
            metavar="SESSION",
            default=None,
            help=(
                'Read the job\'s testcase.lock from this session (name, prefix, or "latest") '
                "instead of the job's most recent run"
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
        epilog = (self.epilog or "").replace("[pad]", "  ")
        print(f"{self.description}\n\n{epilog}")
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


def _warn_if_superseded(workspace: Workspace, jobid: str) -> None:
    """Note on stderr when a job has results from more than one session.

    ``canary query job`` without ``--session`` shows the latest run; earlier
    sessions' results for the same job ID are easy to mistake for it.
    """
    try:
        job = workspace.find_job(jobid)
        sessions = [row["session"] for row in job_result_history(workspace, job.id)]
    except Exception:  # nosec B110 — the note is advisory; never fail the query over it
        return
    if len(sessions) < 2:
        return
    earlier = ", ".join(sessions[:-1])
    sys.stderr.write(
        f"note: job {job.id[:7]} has results from {len(sessions)} sessions; "
        f"showing the latest ({sessions[-1]}). Earlier: {earlier}. "
        "Use --session S to select one, or --all-runs for the history.\n"
    )


# ---------------------------------------------------------------------------
# --where predicate parser
# ---------------------------------------------------------------------------


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
        info = job_blockers(
            workspace,
            args.jobid,
            recursive=getattr(args, "recursive", False),
            signatures=getattr(args, "signatures", False),
        )
        print_json(info, terse=args.terse)
        return 0

    session = getattr(args, "session", None)

    if getattr(args, "missing_inputs", False):
        lockfile = job_lockfile(workspace, args.jobid, session=session)
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
        out: list[dict[str, Any]] = [row_to_job_entry(workspace, row) for row in history]
        print_json(out, terse=args.terse)
        return 0

    if args.cache:
        job = workspace.find_job(args.jobid)
        cache_path = find_cache_path(job)
        if cache_path is None:
            sys.stderr.write(f"No cache entry found for job {args.jobid!r}\n")
            return 1
        data = json.loads(cache_path.read_text())
        print_json(data, terse=args.terse)
        return 0

    lockfile = job_lockfile(workspace, args.jobid, session=session)
    if session is None:
        _warn_if_superseded(workspace, args.jobid)
    data = json.loads(lockfile.read_text())

    # Merge env.json as a top-level "env" key so that path expressions like
    # "env" and "env.CUDA_VISIBLE_DEVICES" work identically to "measurements"
    # and "measurements.flux".  The file is loaded lazily — only when the
    # query path starts with "env" — so queries that don't touch env pay no
    # filesystem cost.
    path = args.path.lstrip(".")
    if path == "env" or path.startswith(("env.", "env[")):
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
        result = clean(result)
    print_json(result, terse=args.terse)
    return 0


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
        rows = db_results_for_session(workspace, session_name)
        missing: list[dict[str, Any]] = []
        for row in rows:
            job = workspace.find_job(row["id"])
            lock_data = json.loads(job.lockfile.read_text())
            inputs = lock_data.get("measurements", {}).get("data", {}).get("inputs", [])
            missing.extend(item for item in inputs if not item.get("exists_now"))
        result = missing
    if args.clean:
        result = clean(result)
    print_json(result, terse=args.terse)
    return 0


def _exec_session_expand(workspace: Workspace, session_dir: Path, args: argparse.Namespace) -> int:
    """Join session job_ids to DB result rows and emit as a JSON array."""
    lockfile = session_dir / "session.lock"
    if not lockfile.exists():
        raise FileNotFoundError(lockfile)
    session_data = json.loads(lockfile.read_text())
    session_name = session_data.get("name", session_dir.name)
    predicate = parse_where(args.where) if args.where else None
    digest = getattr(args, "digest", False)
    watch_interval = getattr(args, "watch", None)

    def _fetch() -> tuple[list[dict[str, Any]], int]:
        rows = db_results_for_session(workspace, session_name)
        out: list[dict[str, Any]] = []
        for row in rows:
            entry = row_to_job_entry(workspace, row)
            apply_with_fields(workspace, row, entry, getattr(args, "with_fields", None) or ["logs"])
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
    predicate = parse_where(args.where) if args.where else None

    out: list[dict[str, Any]] = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        lockfile = session_dir / "session.lock"
        if not lockfile.exists():
            continue
        session_data = json.loads(lockfile.read_text())
        session_name = session_data.get("name", session_dir.name)

        counts = db_outcome_counts_for_session(workspace, session_name)
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
    predicate = parse_where(args.where) if args.where else None
    session_arg = getattr(args, "session", None)
    digest = getattr(args, "digest", False)
    watch_interval = getattr(args, "watch", None)

    def _fetch() -> tuple[list[dict[str, Any]], int]:
        if session_arg is not None:
            session_dir = _resolve_session_dir(workspace, session_arg)
            rows = db_results_for_session(workspace, session_dir.name)
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
            entry = row_to_job_entry(workspace, row)
            apply_with_fields(workspace, row, entry, getattr(args, "with_fields", None) or ["logs"])
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
    rows = db_results_for_session(workspace, session_dir.name)
    predicate = parse_where(args.where) if args.where else None
    if predicate is not None:
        rows = [row for row in rows if predicate(row_to_job_entry(workspace, row))]
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
    base_rows = rows_for_named_session(workspace, args.base_session)
    new_rows = rows_for_named_session(workspace, args.new_session)
    by_name = getattr(args, "by", "spec_id") == "name"
    include_signatures = getattr(args, "signatures", False)

    def key_for(row: dict[str, Any]) -> str:
        return row["spec_name"] if by_name else row["id"]

    base_map = {key_for(row): row for row in base_rows}
    new_map = {key_for(row): row for row in new_rows}
    all_keys = sorted(set(base_map) | set(new_map))
    predicate = parse_where(args.where) if args.where else None

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
        compare_row = build_compare_row(
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
            digest_rows.append(compare_digest(compare_row))

    if getattr(args, "digest", False):
        for line in digest_rows:
            sys.stdout.write(line + "\n")
        return 0

    print_json(result, terse=args.terse)
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
