# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""SQLite-backed workspace database for spec storage, result persistence, and selections.

The :class:`WorkspaceDatabase` manages a single ``workspace.sqlite3`` file at
the workspace root.  It stores four main collections:

* **specs** — serialised :class:`~_canary.jobspec.JobSpec` blobs indexed by
  content-independent spec ID.
* **spec_deps** — dependency edges between specs.
* **results** — per-job execution results keyed by ``(spec_id, session)``.
* **selections** — named tag → spec_id membership sets (used for ``canary tag``).

The :class:`ResultListener` is a daemon thread that drains a file-system spool
queue (:class:`~_canary.util.multiprocessing.FSQueue`) and writes results in
batches, decoupling worker processes from direct SQLite access.

:class:`PartialSpec` is a lightweight projection of the spec + latest-result
data returned by :meth:`WorkspaceDatabase.get_partial_specs`.  It is used by
rerun strategies to decide which specs to re-execute without loading full
``JobSpec`` objects.
"""

import collections
import dataclasses
import datetime
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterable

from . import jobspec
from .job import JobPhase
from .job import JobState
from .jobspec import JobSpec
from .jobspec_graph import make_spec_graph
from .status import Status
from .util import json_helper as json
from .util import logging
from .util.multiprocessing import FSQueue

if TYPE_CHECKING:
    from .job import Job


logger = logging.get_logger(__name__)


class WorkspaceDatabase:
    """SQLite wrapper for the canary workspace database.

    Manages schema creation, spec/result/selection CRUD, dependency graph
    queries, and backward-compatibility migrations.

    The database file lives at ``<workspace_root>/workspace.sqlite3``.  Use
    :meth:`create` to initialise a new database or :meth:`load` to attach to
    an existing one.

    Attributes:
        root: Root directory of the workspace.
        path: Absolute path to the SQLite database file.
        queue: :class:`~_canary.util.multiprocessing.FSQueue` spool directory
            used by worker processes to submit results asynchronously.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.queue = FSQueue(self.root / "tmp/db")
        self.path = root / "workspace.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = None
        self._ready: bool = False

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the active SQLite connection, lazily opening it if necessary."""
        if self._connection is None:
            self.connect()
        assert self._connection is not None
        return self._connection

    def listener(self) -> "ResultListener":
        """Return a new :class:`ResultListener` thread bound to this database."""
        return ResultListener(self)

    def close(self) -> None:
        """Close the SQLite connection if it is open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @classmethod
    def create(cls, path: Path) -> "WorkspaceDatabase":
        """Create a new workspace database at *path* and return it.

        Calls :meth:`connect` immediately, which creates the schema tables if
        they do not yet exist.
        """
        self = cls(path)
        self.connect()
        return self

    @classmethod
    def load(cls, path: Path) -> "WorkspaceDatabase":
        """Attach to an existing workspace database at *path*.

        The connection is not opened until the first query; use
        :meth:`connect` to open it eagerly.
        """
        self = cls(path)
        return self

    def connect(self) -> None:
        """Open the SQLite connection and create or migrate the schema.

        This method is idempotent — calling it multiple times has no effect if
        the connection is already open.  The schema is created with
        ``CREATE TABLE IF NOT EXISTS`` guards so it is safe to call on an
        existing database.
        """
        if self._connection is None:
            self._connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
            self._connection.execute("PRAGMA journal_mode=MEMORY;")
            self._connection.execute("PRAGMA synchronous=OFF;")
            self._connection.execute("PRAGMA foreign_key=ON;")
        assert self._connection is not None
        conn = self._connection
        with conn:
            sql = "CREATE TABLE IF NOT EXISTS specs (spec_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
            conn.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS specs_meta (
              spec_id TEXT PRIMARY KEY,
              source TEXT NOT NULL,
              view TEXT NOT NULL
            )"""
            conn.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_meta_src ON specs_meta (source)"
            conn.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_meta_view ON specs_meta (view)"
            conn.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS spec_deps (
              spec_id TEXT NOT NULL,
              dep_id TEXT NOT NULL,
              PRIMARY KEY (spec_id, dep_id),
              FOREIGN KEY (spec_id) REFERENCES specs(spec_id) ON DELETE CASCADE
              FOREIGN KEY (dep_id)  REFERENCES specs(spec_id)
            )"""
            conn.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_deps_spec_id ON spec_deps (spec_id)"
            conn.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_deps_dep_id ON spec_deps (dep_id)"
            conn.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS selections (
              tag TEXT,
              spec_id TEXT,
              PRIMARY KEY (tag, spec_id),
              FOREIGN KEY (tag) REFERENCES selections(spec_id) ON DELETE CASCADE
            )"""
            conn.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS selection_meta (
              tag TEXT PRIMARY KEY,
              data TEXT
            )"""
            conn.execute(sql)

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_selection_meta_delete
                AFTER DELETE ON selections
                WHEN NOT EXISTS (
                  SELECT 1 FROM selections WHERE tag = OLD.tag
                )
                BEGIN
                  DELETE FROM selection_meta WHERE tag = OLD.tag;
                END;
                """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_selection_meta_rename
                AFTER UPDATE ON selections
                BEGIN
                  UPDATE selection_meta SET tag = NEW.tag WHERE tag = OLD.tag;
                END;
                """
            )

            sql = """CREATE TABLE IF NOT EXISTS results (
            spec_id TEXT,
            spec_name TEXT,
            spec_fullname TEXT,
            file_root TEXT,
            file_path TEXT,
            session TEXT,
            workspace TEXT,
            job_state TEXT,
            status_category TEXT,
            status_outcome TEXT,
            status_reason TEXT,
            status_code INTEGER,
            timekeeper TEXT,
            measurements TEXT,
            PRIMARY KEY (spec_id, session)
            )"""
            conn.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_results_id ON results (spec_id)"
            conn.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_results_session ON results (session)"
            conn.execute(sql)

        _migrate_results_status_state_to_job_state(self)
        return

    def put_specs(self, specs: list[JobSpec]) -> None:
        """Upsert *specs* into the database, replacing any previous blobs.

        Also updates ``specs_meta`` (source file path and view path) and
        rebuilds the ``spec_deps`` edges for the given specs.

        Args:
            specs: The specs to store.  Serialisation is parallelised over a
                thread pool for large collections.
        """

        def process_one_spec(spec: JobSpec) -> tuple[str, str, str, str, list[str]]:
            blob = json.dumps_min(spec)
            view = spec.exec_path / spec.file.name
            source = spec.file
            dep_ids = [dep.spec.id for dep in spec.dependencies]
            return spec.id, blob, source.as_posix(), view.as_posix(), dep_ids

        data = []
        with ThreadPoolExecutor() as ex:
            futures = [ex.submit(process_one_spec, spec) for spec in specs]
            for future in as_completed(futures):
                data.append(future.result())

        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _ids(id TEXT PRIMARY KEY)")
            self.connection.executemany("INSERT INTO _ids(id) VALUES (?)", ((_[0],) for _ in data))
            # 2. Bulk insert/update specs
            self.connection.executemany(
                """
                INSERT INTO specs (spec_id, data)
                VALUES (?, ?)
                ON CONFLICT(spec_id) DO UPDATE SET data=excluded.data
                """,
                ((row[0], row[1]) for row in data),
            )

            self.connection.execute("CREATE TEMP TABLE _meta(spec_id TEXT, source TEXT, view TEXT)")

            self.connection.executemany(
                """
                INSERT INTO _meta(spec_id, source, view)
                VALUES (?, ?, ?)
                """,
                ((row[0], row[2], row[3]) for row in data),
            )

            self.connection.execute(
                """
                INSERT OR REPLACE INTO specs_meta(spec_id, source, view)
                SELECT spec_id, source, view
                FROM _meta
                """
            )
            self.connection.execute("DROP TABLE _meta")

            # 3. Bulk delete old dependencies for these specs
            self.connection.execute("DELETE FROM spec_deps WHERE spec_id IN (SELECT id FROM _ids)")

            # 4. Bulk insert new dependencies using generator (minimal memory)
            if graph := [(row[0], dep_id) for row in data for dep_id in row[-1]]:
                self.connection.executemany(
                    "INSERT INTO spec_deps(spec_id, dep_id) VALUES (?, ?)", graph
                )

            # 5. Drop temporary table
            self.connection.execute("DROP TABLE _ids")

    def resolve_spec_id(self, id: str) -> str | None:
        """Expand a short spec ID prefix to its full 64-character ID.

        Args:
            id: A hex prefix (any length up to 64 chars).  A leading ``@``
                sigil is stripped before lookup.

        Returns:
            The full spec ID if exactly one spec matches, or ``None`` if no
            match is found.

        Raises:
            ValueError: If the prefix is ambiguous (matches more than one spec).
        """
        if id.startswith(jobspec.select_sygil):
            id = id[1:]
        try:
            hi = increment_hex_prefix(id)
        except ValueError:
            return None
        if hi is None:
            return None
        sql = "SELECT spec_id FROM specs WHERE spec_id >= ? AND spec_id < ? LIMIT 2"
        rows = self.connection.execute(sql, (id, hi)).fetchall()
        if len(rows) == 0:
            return None
        elif len(rows) > 1:
            raise ValueError(f"Ambiguous spec ID {id!r}")
        return rows[0][0]

    def resolve_spec_ids(self, ids: list[str]):
        """Expand short spec ID prefixes in *ids* to their full 64-char IDs in-place.

        Args:
            ids: List of spec IDs (partial or full).  Modified in place; full
                IDs are left unchanged.

        Raises:
            ValueError: If any prefix matches no specs or matches more than one.
        """
        for i, id in enumerate(ids):
            if id.startswith(jobspec.select_sygil):
                id = id[1:]
            if len(id) >= 64:
                continue
            hi = increment_hex_prefix(id)
            assert hi is not None
            cur = self.connection.execute(
                """
                SELECT spec_id
                FROM specs
                WHERE spec_id >= ? AND spec_id < ?
                ORDER BY spec_id LIMIT 2
                """,
                (id, hi),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"No match for spec ID {id!r}")
            if cur.fetchone():
                raise ValueError(f"Ambiguous spec ID {id!r}")
            ids[i] = row[0]

    def load_specs(
        self, ids: list[str] | None = None, include_upstreams: bool = False
    ) -> list[JobSpec]:
        """Load and deserialise :class:`~_canary.jobspec.JobSpec` objects from the database.

        Args:
            ids: Spec IDs to load.  ``None`` loads all specs.  Short prefixes
                are expanded via :meth:`resolve_spec_ids`.
            include_upstreams: If ``True``, upstream prerequisite specs are
                included in the returned list even if they are not in *ids*.

        Returns:
            Specs in topological order (dependencies before dependants).
        """
        if not ids:
            rows = self.connection.execute("SELECT * FROM specs").fetchall()
            return self._reconstruct_specs(rows)
        self.resolve_spec_ids(ids)
        upstream = self.get_upstream_ids(ids)
        load_ids = upstream.union(ids)
        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _ids (id TEXT PRIMARY KEY)")
            self.connection.executemany("INSERT INTO _ids(id) VALUES (?)", ((_,) for _ in load_ids))
            rows = self.connection.execute(
                "SELECT * FROM specs where spec_id IN (SELECT id FROM _ids)"
            ).fetchall()
            self.connection.execute("DROP TABLE _ids")
        specs = self._reconstruct_specs(rows)
        if include_upstreams:
            return specs
        return [spec for spec in specs if spec.id in ids]

    def load_specs_by_tagname(self, tag: str) -> list["JobSpec"]:
        """Load specs that belong to the named selection *tag*.

        Args:
            tag: Selection tag name.

        Returns:
            Specs in topological order.

        Raises:
            NotASelection: If *tag* does not exist in the database.
        """
        rows = self.connection.execute(
            """
            SELECT s.spec_id, s.data
            FROM specs s
            JOIN selections ss ON ss.spec_id = s.spec_id
            WHERE ss.tag = ?
            """,
            (tag,),
        ).fetchall()
        if not rows:
            raise NotASelection(tag)
        return self._reconstruct_specs(rows)

    def _reconstruct_specs(self, rows: list[tuple[str, bytes]]) -> list[JobSpec]:
        """Deserialise spec rows and rehydrate dependency references.

        Dependency links stored in ``spec_deps`` are reconnected so each spec's
        ``spec.dependencies[i].spec`` points to the actual ``JobSpec`` object.
        """
        spec: JobSpec
        specs: dict[str, JobSpec] = {}
        imap: dict[str, dict[str, int]] = {}
        for row in rows:
            spec = json.loads(row[-1])
            specs[spec.id] = spec
            imap[spec.id] = {dep.spec.id: i for i, dep in enumerate(spec.dependencies)}
        ids = [spec.id for spec in specs.values()]
        edges = self.get_edges(ids)
        for spec_id, dep_id in edges:
            specs[spec_id].dependencies[imap[spec_id][dep_id]].spec = specs[dep_id]
        graph = make_spec_graph(list(specs.values()))
        return list(graph.topo_order())

    def get_edges(self, ids: list[str] | None = None) -> list[tuple[str, str]]:
        """Return ``(spec_id, dep_id)`` pairs from the ``spec_deps`` table.

        Args:
            ids: Restrict results to these spec IDs.  ``None`` returns all edges.
        """
        if not ids:
            return self.connection.execute("SELECT spec_id, dep_id FROM spec_deps").fetchall()
        rows: list[tuple[str, str]]
        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _ids (id TEXT PRIMARY KEY)")
            self.connection.executemany("INSERT INTO _ids(id) VALUES (?)", ((_,) for _ in ids))
            rows = self.connection.execute(
                "SELECT spec_id, dep_id FROM spec_deps WHERE spec_id IN (SELECT id FROM _ids)"
            ).fetchall()
            self.connection.execute("DROP TABLE _ids")
        return rows

    @staticmethod
    def format_single_result(job: "Job") -> tuple[Any, ...]:
        """Serialise *job* into a flat tuple suitable for ``INSERT INTO results``."""
        phase = job.state.phase
        if isinstance(phase, str):
            phase = JobPhase(phase)
        row = (
            job.id,
            job.spec.name,
            job.spec.fullname,
            str(job.spec.file_root),
            str(job.spec.file_path),
            str(job.workspace.session),
            str(job.workspace.path),
            phase.value,
            job.status.category.value,
            job.status.outcome.name,
            job.status.reason or "",
            job.status.code,
            json.dumps_min(job.timekeeper),
            json.dumps_min(job.measurements),
        )
        return row

    def put_result(self, job: "Job") -> None:
        """Store a single job result; convenience wrapper around :meth:`put_results`."""
        return self.put_results(job)

    def put_results(self, *jobs: "Job") -> None:
        """Store one or more job results in the database.

        Each job is serialised via :meth:`format_single_result` and upserted
        into the ``results`` table keyed by ``(spec_id, session)``.  A
        ``INSERT OR REPLACE`` strategy is used so re-runs within the same
        session overwrite the previous entry.

        Args:
            *jobs: One or more :class:`~_canary.job.Job` objects to persist.
        """

        rows = [self.format_single_result(job) for job in jobs]
        sql = """
        INSERT OR REPLACE INTO results (
          spec_id, spec_name, spec_fullname, file_root, file_path, session, workspace,
          job_state, status_category, status_outcome, status_reason, status_code,
          timekeeper, measurements
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.connection:
            self.connection.executemany(sql, rows)

    def get_results(
        self, ids: list[str] | None = None, include_upstreams: bool = False
    ) -> dict[str, dict[str, Any]]:
        """Return the latest result record for each spec as a plain dict.

        Args:
            ids: Restrict results to these spec IDs.  ``None`` returns all specs.
            include_upstreams: Also include upstream prerequisite specs.

        Returns:
            Mapping of spec_id → result dict (see :meth:`_reconstruct_results`
            for the dict schema).
        """
        rows: list[tuple[str, ...]]
        if not ids:
            with self.connection:
                rows = self.connection.execute(
                    """SELECT *
                    FROM results AS r
                    WHERE r.session = (
                      SELECT MAX(session)
                      FROM results AS r2
                      WHERE r2.spec_id = r.spec_id
                    )
                    """
                ).fetchall()
            return {row[0]: self._reconstruct_results(row) for row in rows}
        self.resolve_spec_ids(ids)
        upstream = self.get_upstream_ids(ids) if include_upstreams else set()
        load_ids = list(upstream.union(ids))
        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _ids (id TEXT PRIMARY KEY)")
            self.connection.executemany("INSERT INTO _ids(id) VALUES (?)", ((_,) for _ in load_ids))
            rows = self.connection.execute(
                """
                SELECT r.*
                FROM results AS r
                WHERE r.spec_id IN (SELECT id FROM _ids)
                AND r.session = (
                  SELECT MAX(session)
                  FROM results AS r2
                  WHERE r2.spec_id = r.spec_id
                )
                """
            ).fetchall()
            self.connection.execute("DROP TABLE _ids")
        return {row[0]: self._reconstruct_results(row) for row in rows}

    def get_result_history(self, id: str) -> list:
        """Return all historical result records for *id* in ascending session order.

        Args:
            id: Full or prefix spec ID.

        Returns:
            List of result dicts (see :meth:`_reconstruct_results`), oldest first.
        """
        rows = self.connection.execute(
            "SELECT * FROM results WHERE spec_id LIKE ? ORDER BY session ASC", (f"{id}%",)
        ).fetchall()
        data: list[dict] = []
        for row in rows:
            d = self._reconstruct_results(row)
            data.append(d)
        return data

    def _reconstruct_results(self, row: tuple[Any, ...]) -> dict[str, Any]:
        """Convert a raw ``results`` table row into a structured result dict.

        Returns a dict with keys: ``id``, ``spec_name``, ``spec_fullname``,
        ``file_root``, ``file_path``, ``session``, ``workspace``, ``state``
        (:class:`~_canary.job.JobState`), ``status``
        (:class:`~_canary.status.Status`), ``timekeeper``
        (:class:`~_canary.timekeeper.Timekeeper`), and ``measurements``.
        """
        d: dict[str, Any] = {}
        d["id"] = row[0]
        d["spec_name"] = row[1]
        d["spec_fullname"] = row[2]
        d["file_root"] = row[3]
        d["file_path"] = row[4]
        d["session"] = row[5]
        d["workspace"] = row[6]
        d["state"] = JobState(phase=JobPhase(row[7]))
        d["status"] = Status.from_dict(
            {"category": row[8], "outcome": row[9], "reason": row[10], "code": row[11]}
        )
        d["timekeeper"] = json.loads(row[12])
        d["measurements"] = json.loads(row[13])
        return d

    def put_selection(self, tag: str, specs: list["JobSpec"], **meta: Any) -> None:
        """Store a named selection (tag) mapping *tag* → spec IDs.

        Replaces any existing selection with the same name.  The reserved tag
        ``':all:'`` is rejected with ``ValueError``.

        Args:
            tag: Selection name.
            specs: Specs to include in the selection.
            **meta: Additional metadata key/value pairs stored in
                ``selection_meta``.
        """
        if tag == ":all:":
            raise ValueError("Tag name :all: is reserved")
        with self.connection:
            self.connection.execute("DELETE FROM selections WHERE tag = ?", (tag,))
            self.connection.execute("DELETE FROM selection_meta WHERE tag = ?", (tag,))
            self.connection.executemany(
                """
                INSERT INTO selections (tag, spec_id)
                VALUES (?, ?)
                """,
                ((tag, spec.id) for spec in specs),
            )
            meta["created_on"] = datetime.datetime.now().isoformat()
            self.connection.execute(
                """
                INSERT INTO selection_meta (tag, data)
                VALUES (?, ?)
                """,
                (tag, json.dumps_min(meta, sort_keys=True)),
            )

    def rename_selection(self, old: str, new: str) -> None:
        """Rename selection *old* to *new* (updates both ``selections`` and ``selection_meta``)."""
        with self.connection:
            self.connection.execute("UPDATE selections SET tag = ? WHERE tag = ?", (new, old))

    def get_selection_metadata(self, tag: str) -> dict[str, Any]:
        """Return the metadata dict for selection *tag*.

        Raises:
            NotASelection: If *tag* does not exist.
        """
        if not self.is_selection(tag):
            raise NotASelection(f"{tag} is not a selection")
        text = self.connection.execute(
            "SELECT data FROM selection_meta WHERE tag = ? LIMIT 1", (tag,)
        ).fetchone()
        meta = json.loads(text[0])
        meta["tag"] = tag
        return meta

    @property
    def tags(self) -> list[str]:
        """List of all selection tag names, sorted alphabetically."""
        rows = self.connection.execute(
            "SELECT DISTINCT tag FROM selections ORDER BY tag"
        ).fetchall()
        return [row[0] for row in rows]

    def is_selection(self, tag: str) -> bool:
        """Return ``True`` if *tag* names an existing selection."""
        cur = self.connection.execute("SELECT 1 FROM selections WHERE tag = ? LIMIT 1", (tag,))
        return cur.fetchone() is not None

    def delete_selection(self, tag: str) -> bool:
        """Delete the selection *tag* from the database.

        Returns:
            Always ``True`` (the deletion is unconditional).
        """
        with self.connection:
            self.connection.execute("DELETE FROM selections WHERE tag = ?", (tag,))
        return True

    def get_updownstream_ids(self, seeds: list[str] | None = None) -> tuple[set[str], set[str]]:
        """Return both the upstream prerequisites and downstream dependants of *seeds*.

        Args:
            seeds: Seed spec IDs.

        Returns:
            A ``(upstream, downstream)`` tuple of spec ID sets.  ``upstream``
            contains all prerequisites of the full reachable set (seeds +
            downstream); ``downstream`` contains all transitive dependants.
        """
        if seeds is None:
            return set(), set()
        downstream = self.get_downstream_ids(seeds)
        upstream = self.get_upstream_ids(downstream.union(seeds))
        return upstream, downstream

    def get_downstream_ids(self, seeds: Iterable[str]) -> set[str]:
        """Return all transitive dependants of *seeds* (specs that depend on them).

        Uses a recursive CTE to traverse ``spec_deps`` in the forward direction.
        """
        if not seeds:
            return set()
        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _ids (id TEXT PRIMARY KEY)")
            self.connection.executemany("INSERT INTO _ids(id) VALUES (?)", ((s,) for s in seeds))
            sql = """
                WITH RECURSIVE
                downstream(id) AS (
                  SELECT spec_id
                  FROM spec_deps
                  WHERE dep_id IN (SELECT id FROM _ids)
                  UNION
                  SELECT d.spec_id
                  FROM spec_deps d
                  JOIN downstream dn ON d.dep_id = dn.id
                )
                SELECT DISTINCT id FROM downstream
            """
            rows = self.connection.execute(sql).fetchall()
            self.connection.execute("DROP TABLE _ids")
        return {r[0] for r in rows}

    def get_upstream_ids(self, seeds: Iterable[str]) -> set[str]:
        """Return all transitive prerequisites of *seeds* (specs they depend on).

        Uses a recursive CTE to traverse ``spec_deps`` in the reverse direction.
        """
        if not seeds:
            return set()
        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _ids (id TEXT PRIMARY KEY)")
            self.connection.executemany("INSERT INTO _ids(id) VALUES (?)", ((s,) for s in seeds))
            sql = """
                WITH RECURSIVE
                upstream(id) AS (
                  SELECT dep_id
                  FROM spec_deps
                  WHERE spec_id IN (SELECT id FROM _ids)
                  UNION
                  SELECT d.dep_id
                  FROM spec_deps d
                  JOIN upstream u ON d.spec_id = u.id
                )
                SELECT DISTINCT id FROM upstream
            """
            rows = self.connection.execute(sql).fetchall()
            self.connection.execute("DROP TABLE _ids")
        return {r[0] for r in rows}

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """
        Return the entire dependency graph, including disconnected nodes.
        Every spec appears, standalone nodes have dep_id=None (empty list).
        """
        graph: dict[str, list[str]] = collections.defaultdict(list)
        rows = self.connection.execute("SELECT spec_id FROM specs").fetchall()
        for (spec_id,) in rows:
            graph[spec_id] = []
        rows = self.connection.execute("SELECT spec_id, dep_id FROM spec_deps").fetchall()
        for spec_id, dep_id in rows:
            graph[spec_id].append(dep_id)
        return graph

    def get_partial_specs(self, *, tag: str | None = None) -> list["PartialSpec"]:
        """Return lightweight :class:`PartialSpec` summaries for all (or tagged) specs.

        Joins ``specs``, ``specs_meta``, and the latest ``results`` row for each
        spec into a single query.  Used by rerun strategies to decide which specs
        to re-execute without deserialising full ``JobSpec`` blobs.

        Args:
            tag: If given, restrict to specs that belong to this selection.
                The special value ``':all:'`` is normalised to ``None``.
        """
        if tag == ":all:":
            tag = None
        clauses: list[str] = []
        params: list[str] = []
        join = ""
        if tag is not None:
            join = """
            JOIN selections ss ON ss.spec_id = s.spec_id
            """
            clauses.append("ss.tag = ?")
            params.append(tag)
        where = "" if not clauses else "WHERE " + " AND ".join(clauses)
        sql = f"""
        WITH latest_session AS (
          SELECT spec_id, MAX(session) AS session
          FROM results
          GROUP BY spec_id
        ),
        latest_results AS (
          SELECT
            r.spec_id,
            r.timekeeper,
            r.status_category,
            r.status_outcome,
            r.status_reason,
            r.status_code
          FROM results r
          JOIN latest_session ls
          ON r.spec_id = ls.spec_id
          AND r.session = ls.session
        )
        SELECT
          s.spec_id,
          sm.source,
          sm.view,
          lr.timekeeper,
          lr.status_category,
          lr.status_outcome,
          lr.status_reason,
          lr.status_code
        FROM specs s
        JOIN specs_meta sm
          ON sm.spec_id = s.spec_id
        LEFT JOIN latest_results lr
          ON lr.spec_id = s.spec_id
        {join}
        {where}
        """  # nosec B608
        rows = self.connection.execute(sql, params).fetchall()
        candidates: list[PartialSpec] = []
        for row in rows:
            start: float = self._timekeeper_started_at(row[3])
            c = PartialSpec(
                id=row[0],
                file=Path(row[1]),
                view=row[2],
                started_at=start,
                result_category=row[4],
                result_outcome=row[5],
            )
            candidates.append(c)
        return candidates

    def select_from_view(self, prefixes: list[str]) -> list[str]:
        """
        Return spec IDs whose view matches ANY of the provided glob patterns.

        `view` is stored as a TestResults-relative path, e.g.:
          foo/bar/test_case.py

        """
        if not prefixes:
            return []
        clauses = ["view LIKE ?" if p.endswith("%") else "view = ?" for p in prefixes]
        sql = f"""
            SELECT DISTINCT spec_id
            FROM specs_meta
            WHERE {" OR ".join(clauses)}
        """  # nosec B608
        rows = self.connection.execute(sql, prefixes).fetchall()
        return [row[0] for row in rows]

    def _timekeeper_started_at(self, text: str | None) -> float:
        """Extract the earliest meaningful timestamp from a serialised :class:`Timekeeper`.

        Returns the first positive value among ``_started``, ``_submitted``, and
        ``_finished``, or ``-1.0`` if the text is absent or unparseable.
        """
        if not text:
            return -1.0
        try:
            tk = json.loads(text)
        except Exception:
            return -1.0
        for name in ("_started", "_submitted", "_finished"):
            value = getattr(tk, name, -1.0)
            try:
                value = float(value)
            except Exception:
                value = -1.0
            if value > 0:
                return value
        return -1.0


class ResultListener(threading.Thread):
    """
    Watches a spool directory for JSON test results and writes them to SQLite in batches.
    """

    def __init__(self, db: WorkspaceDatabase, poll_interval: float = 0.05) -> None:
        super().__init__(daemon=True)
        self.db = WorkspaceDatabase.load(db.root)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._processed: set[str] = set()  # Track processed files

    def run(self):
        """Main thread loop."""
        self.db.connect()
        try:
            while not self._stop_event.is_set():
                objs = self.db.queue.drain()
                if objs:
                    self.db.put_results(*objs)
                    self._processed.update([obj.id for obj in objs])
                time.sleep(self.poll_interval)
            objs = self.db.queue.drain()
            if objs:
                self.db.put_results(*objs)
                self._processed.update([obj.id for obj in objs])
        finally:
            self.db.close()

    def stop_and_join(self):
        """Stop listener and wait for thread to finish."""
        self._stop_event.set()
        self.join()


@dataclasses.dataclass
class PartialSpec:
    """Lightweight summary of a spec plus its latest result, used by rerun strategies.

    Attributes:
        id: Full 64-char spec ID.
        file: Absolute path to the test source file.
        view: View-relative path string (e.g. ``'foo/bar/test_case.py'``).
        result_category: String ``Category`` name of the latest result, or
            ``None`` if the spec has never run.
        result_outcome: String ``Outcome`` name of the latest result, or
            ``None`` if the spec has never run.
        started_at: Unix timestamp of the latest execution start (or submission
            / finish if start was not recorded), or ``-1.0`` if never run.
    """

    id: str
    file: Path
    view: str
    result_category: str
    result_outcome: str
    started_at: float


def increment_hex_prefix(prefix: str) -> str | None:
    """Return the next hex string after *prefix* for range queries.

    Used to build ``WHERE spec_id >= prefix AND spec_id < upper`` range
    queries that efficiently expand short prefixes to full IDs.

    Args:
        prefix: A non-empty hex string.

    Returns:
        A hex string of the same length that is numerically one greater than
        *prefix*, or ``None`` if *prefix* is already the maximum value for
        its length (all ``f``\\s).

    Raises:
        ValueError: If *prefix* contains non-hex characters.
    """
    try:
        value = int(prefix, 16)
    except ValueError:
        raise ValueError(f"Ivalid hex prefix: {prefix!r}") from None
    max_value = (1 << (4 * len(prefix))) - 1
    if value == max_value:
        logger.warning("No valid upper bound - prefix overflow")
        return None
    return f"{value + 1:0{len(prefix)}x}"


def is_operation_error(e: BaseException) -> bool:
    """Return ``True`` if *e* is a :class:`sqlite3.OperationalError`."""
    return isinstance(e, sqlite3.OperationalError)


class NotASelection(Exception):
    """Raised when a tag name is not found in the ``selections`` table."""

    def __init__(self, tag):
        super().__init__(f"No selection for tag {tag!r} found")


# Backward compatibility


def _migrate_results_status_state_to_job_state(db: WorkspaceDatabase) -> None:
    """One-time migration: rename the legacy ``status_state`` column to ``job_state``.

    Databases created before the ``job_state`` rename keep a ``status_state``
    column.  This function detects that condition and performs an in-place
    schema migration using a rename-and-copy strategy so that no result data is
    lost.  Safe to call on already-migrated databases (no-op).
    """
    conn = db.connection
    row = conn.execute("SELECT 1 FROM results").fetchone()
    if row is None:
        return
    info = conn.execute("PRAGMA table_info(results)").fetchall()
    cols = {r[1] for r in info}
    if "status_state" not in cols:
        return
    if "job_state" in cols:
        # inconsistent schema; bail or handle separately
        logger.warning("results has both status_state and job_state; skipping migration")
        return
    logger.info("DB migration: results.status_state -> results.job_state")
    with conn:
        # 1) rename old table out of the way
        conn.execute("ALTER TABLE results RENAME TO results_old")

        # 2) create new results table with job_state
        conn.execute(
            """
            CREATE TABLE results (
              spec_id TEXT,
              spec_name TEXT,
              spec_fullname TEXT,
              file_root TEXT,
              file_path TEXT,
              session TEXT,
              workspace TEXT,

              job_state TEXT,

              status_category TEXT,
              status_outcome TEXT,
              status_reason TEXT,
              status_code INTEGER,

              submitted REAL,
              started REAL,
              finished REAL,
              measurements TEXT,

              PRIMARY KEY (spec_id, session)
            )
            """
        )

        # 3) copy data with transformation
        conn.execute(
            """
            INSERT INTO results (
              spec_id, spec_name, spec_fullname, file_root, file_path, session, workspace,
              job_state, status_category, status_outcome, status_reason, status_code,
              submitted, started, finished, measurements
            )
            SELECT
              spec_id, spec_name, spec_fullname, file_root, file_path, session, workspace,
              CASE status_state
                WHEN 'COMPLETE' THEN 'DONE'
                WHEN 'NOTRUN'   THEN 'DONE'
                WHEN 'READY'    THEN 'PENDING'
                WHEN 'PENDING'  THEN 'PENDING'
                WHEN 'RUNNING'  THEN 'RUNNING'
                ELSE 'PENDING'
              END AS job_state,
              status_category, status_status, status_reason, status_code,
              submitted, started, finished, measurements
            FROM results_old
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_results_id ON results (spec_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_results_session ON results (session)")
        conn.execute("DROP TABLE results_old")
