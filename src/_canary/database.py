# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import collections
import dataclasses
import datetime
import hashlib
import pickle  # nosec B403
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterable

from . import testspec
from .status import Status
from .testcase import Measurements
from .testspec import ResolvedSpec
from .timekeeper import Timekeeper
from .util import json_helper as json
from .util import logging
from .version import __static_version__

if TYPE_CHECKING:
    from .workspace import Session

logger = logging.get_logger(__name__)


DB_MAX_RETRIES = 8
DB_BASE_DELAY = 0.05  # 50ms base for exponential backoff (0.05, 0.1, 0.2, ...)
SQL_CHUNK_SIZE = 900


@dataclasses.dataclass
class Selection:
    id: str
    tag: str
    gen_signature: str
    created_on: datetime.datetime
    canary_version: str
    scanpaths: dict[str, list[str]]
    on_options: list[str] | None
    keyword_exprs: list[str] | None
    parameter_expr: str | None
    owners: list[str] | None
    regex: str | None
    fingerprint: str


class WorkspaceDatabase:
    """Database wrapper"""

    connection: sqlite3.Connection

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=MEMORY;")
        self.connection.execute("PRAGMA synchronous=OFF;")
        self.connection.execute("PRAGMA foreign_key=ON;")

    @classmethod
    def create(cls, path: Path) -> "WorkspaceDatabase":
        self = cls(path)
        with self.connection:
            sql = "CREATE TABLE IF NOT EXISTS specs (spec_id TEXT PRIMARY KEY, data BLOB NOT NULL)"
            self.connection.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS specs_meta (
              spec_id TEXT NOT NULL,
              source TEXT NOT NULL,
              view TEXT NOT NULL,
              gen_signature TEXT NOT NULL,
              PRIMARY KEY (spec_id, gen_signature)
            )"""
            self.connection.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_meta_src ON specs_meta (source)"
            self.connection.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_meta_view ON specs_meta (view)"
            self.connection.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS spec_deps (
              spec_id TEXT NOT NULL,
              dep_id TEXT NOT NULL,
              PRIMARY KEY (spec_id, dep_id),
              FOREIGN KEY (spec_id) REFERENCES specs(spec_id) ON DELETE CASCADE
              FOREIGN KEY (dep_id)  REFERENCES specs(spec_id)
            )"""
            self.connection.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_deps_spec_id ON spec_deps (spec_id)"
            self.connection.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_spec_deps_dep_id ON spec_deps (dep_id)"
            self.connection.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS selections (
              id TEXT PRIMARY KEY,
              tag TEXT UNIQUE,
              gen_signature TEXT,
              created_on TEXT,
              canary_version TEXT,
              scanpaths TEXT,
              on_options TEXT,
              keyword_exprs TEXT,
              parameter_expr TEXT,
              owners TEXT,
              regex TEXT,
              fingerprint TEXT
            )
            """
            self.connection.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS selection_specs (
              selection_id TEXT,
              spec_id TEXT,
              PRIMARY KEY (selection_id, spec_id),
              FOREIGN KEY (selection_id) REFERENCES selections(spec_id) ON DELETE CASCADE
            )"""
            self.connection.execute(sql)

            sql = """CREATE TABLE IF NOT EXISTS results (
            spec_id TEXT,
            spec_name TEXT,
            spec_fullname TEXT,
            file_root TEXT,
            file_path TEXT,
            session TEXT,
            status_state TEXT,
            status_category TEXT,
            status_status TEXT,
            status_reason TEXT,
            status_code INTEGER,
            started_on TEXT,
            finished_on TEXT,
            duration TEXT,
            workspace TEXT,
            measurements TEXT,
            PRIMARY KEY (spec_id, session)
            )"""
            self.connection.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_results_id ON results (spec_id)"
            self.connection.execute(sql)

            sql = "CREATE INDEX IF NOT EXISTS ix_results_session ON results (session)"
            self.connection.execute(sql)

        return self

    @classmethod
    def load(cls, path: Path) -> "WorkspaceDatabase":
        self = cls(path)
        return self

    def close(self):
        self.connection.close()

    def put_specs(self, gen_signature: str, specs: list[ResolvedSpec]) -> None:
        spec_rows: list[tuple[str, bytes]] = []
        meta_rows: list[tuple[str, str, str, str]] = []
        dep_rows: list[tuple[str, str]] = []
        for spec in specs:
            try:
                deps = spec.dependencies
                spec.dependencies = []
                blob = pickle.dumps(spec, protocol=pickle.HIGHEST_PROTOCOL)
            finally:
                spec.dependencies = deps
            spec_rows.append((spec.id, blob))
            view = Path(spec.execpath) / spec.file.name
            source = spec.file
            meta_rows.append((spec.id, source.as_posix(), view.as_posix(), gen_signature))
            for dep in spec.dependencies:
                dep_rows.append((spec.id, dep.id))

        with self.connection:
            self.connection.execute("CREATE TEMP TABLE _spec_ids(id TEXT PRIMARY KEY)")
            self.connection.executemany(
                "INSERT INTO _spec_ids(id) VALUES (?)",
                ((spec.id,) for spec in specs),
            )
            # 2. Bulk insert/update specs
            self.connection.executemany(
                """
                    INSERT INTO specs (spec_id, data)
                    VALUES (?, ?)
                    ON CONFLICT(spec_id) DO UPDATE SET data=excluded.data
                    """,
                spec_rows,
            )

            self.connection.execute(
                """CREATE TEMP TABLE _meta_tmp(
                    spec_id TEXT, source TEXT, view TEXT, gen_signature TEXT
                )
                """
            )

            self.connection.executemany(
                """
                INSERT INTO _meta_tmp(spec_id, source, view, gen_signature)
                VALUES (?, ?, ?, ?)
                """,
                meta_rows,
            )

            self.connection.execute(
                """
                INSERT OR REPLACE INTO specs_meta(spec_id, source, view, gen_signature)
                SELECT spec_id, source, view, gen_signature
                FROM _meta_tmp
                """
            )
            self.connection.execute("DROP TABLE _meta_tmp")

            # 3. Bulk delete old dependencies for these specs
            self.connection.execute(
                "DELETE FROM spec_deps WHERE spec_id IN (SELECT id FROM _spec_ids)"
            )

            # 4. Bulk insert new dependencies using generator (minimal memory)
            self.connection.executemany(
                "INSERT INTO spec_deps(spec_id, dep_id) VALUES (?, ?)", dep_rows
            )

            # 5. Drop temporary table
            self.connection.execute("DROP TABLE _spec_ids")

    def resolve_spec_id(self, id: str) -> str | None:
        if id.startswith(testspec.select_sygil):
            id = id[1:]
        try:
            hi = increment_hex_prefix(id)
        except ValueError:
            return None
        if hi is None:
            return None
        rows = self.connection.execute(
            "SELECT spec_id FROM specs WHERE spec_id >= ? AND spec_id < ? LIMIT 2", (id, hi)
        ).fetchall()
        if len(rows) == 0:
            return None
        elif len(rows) > 1:
            raise ValueError(f"Ambiguous spec ID {id!r}")
        return rows[0][0]

    def resolve_spec_ids(self, ids: list[str]):
        """Given partial spec IDs in ``ids``, expand them to their full size"""
        for i, id in enumerate(ids):
            if id.startswith(testspec.select_sygil):
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
    ) -> list[ResolvedSpec]:
        rows: list[tuple[str, bytes]]
        if not ids:
            rows = self.connection.execute("SELECT * FROM specs").fetchall()
            return self._reconstruct_specs(rows)
        self.resolve_spec_ids(ids)
        upstream = self.get_upstream_ids(ids)
        load_ids = list(upstream.union(ids))
        rows = []
        base_sql = "SELECT * FROM specs WHERE spec_id IN"
        for i in range(0, len(load_ids), SQL_CHUNK_SIZE):
            chunk = load_ids[i : i + SQL_CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            sql = f"{base_sql} ({placeholders})"
            cursor = self.connection.execute(sql, chunk)
            rows.extend(cursor.fetchall())
        specs = self._reconstruct_specs(rows)
        if include_upstreams:
            return specs
        return [spec for spec in specs if spec.id in ids]

    def load_specs_by_signature(self, signature: str) -> list[ResolvedSpec]:
        rows = self.connection.execute(
            """
            SELECT s.spec_id, s.data
            FROM specs s
            JOIN specs_meta sm
            ON s.spec_id = sm.spec_id
            where sm.gen_signature = ?
            """,
            (signature,),
        ).fetchall()
        return self._reconstruct_specs(rows)

    def load_specs_by_tagname(self, tag: str) -> list["ResolvedSpec"]:
        rows = self.connection.execute(
            """
            SELECT s.spec_id, s.data
            FROM specs s
            JOIN selection_specs ss ON ss.spec_id = s.spec_id
            JOIN selections sel ON sel.id = ss.selection_id
            WHERE sel.tag = ?
            """,
            (tag,),
        ).fetchall()
        if not rows:
            raise NotASelection(tag)
        return self._reconstruct_specs(rows)

    def _reconstruct_specs(self, rows: list[tuple[str, bytes]]) -> list[ResolvedSpec]:
        specs: dict[str, ResolvedSpec] = {}
        for row in rows:
            spec = pickle.loads(row[-1])  # nosec 301
            spec.dependencies = []
            specs[spec.id] = spec
        ids = [spec.id for spec in specs.values()]
        edges = self.get_edges(ids)
        for spec_id, dep_id in edges:
            specs[spec_id].dependencies.append(specs[dep_id])
        return list(specs.values())

    def get_edges(self, ids: list[str] | None = None) -> list[tuple[str, str]]:
        if not ids:
            return self.connection.execute("SELECT spec_id, dep_id FROM spec_deps").fetchall()
        rows: list[tuple[str, str]] = []
        base_sql = "SELECT spec_id, dep_id FROM spec_deps WHERE spec_id IN"
        for i in range(0, len(ids), SQL_CHUNK_SIZE):
            chunk = ids[i : i + SQL_CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            sql = f"{base_sql} ({placeholders})"
            cursor = self.connection.execute(sql, chunk)
            rows.extend(cursor.fetchall())
        return rows

    def put_results(self, session: "Session") -> None:
        """Store results in the DB.  We store status, timekeeper across columns for future
        enhancements to use results without actually creating a testcase to hold them
        """
        rows = []
        for case in session.cases:
            rows.append(
                (
                    case.id,
                    case.spec.name,
                    case.spec.fullname,
                    str(case.spec.file_root),
                    str(case.spec.file_path),
                    session.name,
                    case.status.state,
                    case.status.category,
                    case.status.status,
                    case.status.reason or "",
                    case.status.code,
                    case.timekeeper.started_on,
                    case.timekeeper.finished_on,
                    case.timekeeper.duration,
                    str(case.workspace.path),
                    json.dumps_min(case.measurements.asdict()),
                )
            )
        with self.connection:
            self.connection.executemany(
                """
                INSERT OR IGNORE INTO results (
                spec_id,
                spec_name,
                spec_fullname,
                file_root,
                file_path,
                session,
                status_state,
                status_category,
                status_status,
                status_reason,
                status_code,
                started_on,
                finished_on,
                duration,
                workspace,
                measurements
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_results(
        self,
        ids: list[str] | None = None,
        include_upstreams: bool = False,
    ) -> dict[str, dict[str, Any]]:
        rows: list[tuple[str, ...]]
        if not ids:
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
        rows = []
        self.resolve_spec_ids(ids)
        upstream = self.get_upstream_ids(ids) if include_upstreams else set()
        load_ids = list(upstream.union(ids))
        for i in range(0, len(load_ids), SQL_CHUNK_SIZE):
            chunk = load_ids[i : i + SQL_CHUNK_SIZE]
            placeholders = ", ".join("?" for _ in chunk)
            sql = f"""\
              SELECT r.*
                FROM results AS r
                WHERE r.spec_id in ({placeholders})
                AND r.session = (
                  SELECT MAX(session)
                  FROM results AS r2
                  WHERE r2.spec_id = r.spec_id
                )
            """  # nosec B608
            cur = self.connection.execute(sql, chunk)  # nosec B608
            rows.extend(cur.fetchall())
        return {row[0]: self._reconstruct_results(row) for row in rows}

    def get_result_history(self, id: str) -> list:
        rows = self.connection.execute(
            "SELECT * FROM results WHERE spec_id LIKE ? ORDER BY session ASC", (f"{id}%",)
        ).fetchall()
        data: list[dict] = []
        for row in rows:
            d = self._reconstruct_results(row)
            data.append(d)
        return data

    def _reconstruct_results(self, row: tuple[str, ...]) -> dict[str, Any]:
        d: dict[str, Any] = {}
        d["id"] = row[0]
        d["spec_name"] = row[1]
        d["spec_fullname"] = row[2]
        d["file_root"] = row[3]
        d["file_path"] = row[4]
        d["session"] = row[5]
        d["status"] = Status.from_dict(
            {
                "state": row[6],
                "category": row[7],
                "status": row[8],
                "reason": row[9],
                "code": row[10],
            }
        )
        d["timekeeper"] = Timekeeper.from_dict(
            {
                "started_on": row[11],
                "finished_on": row[12],
                "duration": float(row[13]),
            }
        )
        d["workspace"] = row[14]
        d["measurements"] = Measurements.from_dict(json.loads(row[15]))
        return d

    def put_selection(
        self,
        tag: str,
        signature: str,
        specs: list["ResolvedSpec"],
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> None:
        if tag == ":all:":
            raise ValueError("Tag name :all: is reserved")
        row: list[str] = []
        id = uuid.uuid4().hex
        row.extend((id, tag, signature, datetime.datetime.now().isoformat(), __static_version__))

        hasher = hashlib.sha256()
        row.append(json.dumps_min(scanpaths, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(on_options, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(keyword_exprs, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(parameter_expr))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(owners, sort_keys=True))
        hasher.update(row[-1].encode())

        row.append(json.dumps_min(regex))
        hasher.update(row[-1].encode())

        fingerprint = hasher.hexdigest()
        row.append(fingerprint)

        with self.connection:
            self.connection.execute("DELETE FROM selections WHERE tag = ?", (tag,))
            self.connection.executemany(
                """
                INSERT INTO selection_specs (selection_id, spec_id)
                VALUES (?, ?)
                """,
                ((id, spec.id) for spec in specs),
            )
            self.connection.execute(
                """
                INSERT INTO selections (
                  id,
                  tag,
                  gen_signature,
                  created_on,
                  canary_version,
                  scanpaths,
                  on_options,
                  keyword_exprs,
                  parameter_expr,
                  owners,
                  regex,
                  fingerprint
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )

    def rename_selection(self, old: str, new: str) -> None:
        with self.connection:
            self.connection.execute("UPDATE selections SET tag = ? WHERE tag = ?", (new, old))

    def get_selection_metadata(self, tag: str) -> "Selection":
        row = self.connection.execute("SELECT * FROM selections WHERE tag = ?", (tag,)).fetchone()
        if not row:
            raise NotASelection(tag)
        return Selection(
            id=row[0],
            tag=row[1],
            gen_signature=row[2],
            created_on=datetime.datetime.fromisoformat(row[3]),
            canary_version=row[4],
            scanpaths=json.loads(row[5]),
            on_options=json.loads(row[6]),
            keyword_exprs=json.loads(row[7]),
            parameter_expr=json.loads(row[8]),
            owners=json.loads(row[9]),
            regex=json.loads(row[10]),
            fingerprint=row[11],
        )

    @property
    def tags(self) -> list[str]:
        rows = self.connection.execute("SELECT tag FROM selections").fetchall()
        return [row[0] for row in rows]

    def is_selection(self, tag: str) -> bool:
        cur = self.connection.execute("SELECT 1 FROM selections WHERE tag = ? LIMIT 1", (tag,))
        return cur.fetchone() is not None

    def delete_selection(self, tag: str) -> bool:
        with self.connection:
            self.connection.execute("DELETE FROM selections WHERE tag = ?", (tag,))
        return True

    def get_updownstream_ids(self, seeds: list[str] | None = None) -> tuple[set[str], set[str]]:
        if seeds is None:
            return set(), set()
        downstream = self.get_downstream_ids(seeds)
        upstream = self.get_upstream_ids(downstream.union(seeds))
        return upstream, downstream

    def get_downstream_ids(self, seeds: Iterable[str]) -> set[str]:
        """Return dependencies in instantiation order."""
        if not seeds:
            return set()
        values = ",".join("(?)" for _ in seeds)
        sql = f"""
        WITH RECURSIVE
        seeds(id) AS (VALUES {values}),
        downstream(id) AS (
          SELECT spec_id
          FROM spec_deps
          WHERE dep_id IN (SELECT id FROM seeds)
          UNION
          SELECT d.spec_id
          FROM spec_deps d
          JOIN downstream dn ON d.dep_id = dn.id
        )
        SELECT DISTINCT id FROM downstream
        """  #  nosec B608
        rows = self.connection.execute(sql, tuple(seeds)).fetchall()
        return {r[0] for r in rows}

    def get_upstream_ids(self, seeds: Iterable[str]) -> set[str]:
        """Return dependents in reverse instantiation order."""
        if not seeds:
            return set()
        seed_vals = tuple(seeds)
        values = ",".join("(?)" for _ in seed_vals)
        sql = f"""
        WITH RECURSIVE
        seeds(id) AS (VALUES {values}),
        upstream(id) AS (
          SELECT dep_id
          FROM spec_deps
          WHERE spec_id IN (SELECT id FROM seeds)
          UNION
          SELECT d.dep_id
          FROM spec_deps d
          JOIN upstream u ON d.spec_id = u.id
        )
        SELECT DISTINCT id FROM upstream
        """  # nosec B608
        rows = self.connection.execute(sql, seed_vals).fetchall()
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
        if tag == ":all:":
            tag = None
        clauses: list[str] = []
        params: list[str] = []
        join = ""
        if tag is not None:
            join = """
            JOIN selection_specs ss ON ss.spec_id = s.spec_id
            JOIN selections sel ON sel.id = ss.selection_id
            """
            clauses.append("sel.tag = ?")
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
            r.finished_on,
            r.status_category,
            r.status_status
          FROM results r
          JOIN latest_session ls
          ON r.spec_id = ls.spec_id
          AND r.session = ls.session
        )
        SELECT
          s.spec_id,
          sm.source,
          sm.view,
          lr.finished_on,
          lr.status_category,
          lr.status_status
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
            start: float = -1
            started_on = row[3]
            if started_on and started_on != "NA":
                start = datetime.datetime.fromisoformat(started_on).timestamp()
            c = PartialSpec(
                id=row[0],
                file=Path(row[1]),
                view=row[2],
                started_at=start,
                result_category=row[4],
                result_status=row[5],
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


@dataclasses.dataclass
class PartialSpec:
    id: str
    file: Path
    view: str
    result_category: str
    result_status: str
    started_at: float


def increment_hex_prefix(prefix: str) -> str | None:
    try:
        value = int(prefix, 16)
    except ValueError:
        raise ValueError(f"Ivalid hex prefix: {prefix!r}") from None
    max_value = (1 << (4 * len(prefix))) - 1
    if value == max_value:
        logger.warning("No valid upper bound - prefix overflow")
        return None
    return f"{value + 1:0{len(prefix)}x}"


class NotASelection(Exception):
    def __init__(self, tag):
        super().__init__(f"No selection for tag {tag!r} found")
