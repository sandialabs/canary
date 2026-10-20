# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Durability, transactional and schema-migration behaviour of the workspace DB."""

import sqlite3
from pathlib import Path

import pytest

from _canary.persistence import database as dbmod
from _canary.persistence.database import SCHEMA_VERSION
from _canary.persistence.database import DatabaseVersionError
from _canary.persistence.database import WorkspaceDatabase


def _pragma(db: WorkspaceDatabase, name: str):
    return db.connection.execute(f"PRAGMA {name}").fetchone()[0]


def test_journal_mode_is_durable(tmp_path: Path):
    db = WorkspaceDatabase.create(tmp_path)
    try:
        assert str(_pragma(db, "journal_mode")).upper() not in ("MEMORY", "OFF")
        # synchronous: 0=OFF, 1=NORMAL, 2=FULL
        assert int(_pragma(db, "synchronous")) >= 1
        assert int(_pragma(db, "foreign_keys")) == 1
    finally:
        db.close()


def test_journal_mode_never_memory_even_if_requested(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CANARY_DB_JOURNAL_MODE", "MEMORY")
    db = WorkspaceDatabase.create(tmp_path)
    try:
        assert str(_pragma(db, "journal_mode")).upper() == "DELETE"
        assert int(_pragma(db, "synchronous")) == 2
    finally:
        db.close()


def test_network_filesystems_use_rollback_journal(monkeypatch):
    monkeypatch.delenv("CANARY_DB_JOURNAL_MODE", raising=False)
    monkeypatch.setattr(dbmod, "_filesystem_type", lambda p: "nfs4")
    assert dbmod._journal_mode_for(Path("/x/y.sqlite3")) == "DELETE"
    monkeypatch.setattr(dbmod, "_filesystem_type", lambda p: "gpfs")
    assert dbmod._journal_mode_for(Path("/x/y.sqlite3")) == "DELETE"
    monkeypatch.setattr(dbmod, "_filesystem_type", lambda p: "ext4")
    assert dbmod._journal_mode_for(Path("/x/y.sqlite3")) == "WAL"


def test_schema_version_recorded(tmp_path: Path):
    db = WorkspaceDatabase.create(tmp_path)
    try:
        assert _pragma(db, "user_version") == SCHEMA_VERSION
    finally:
        db.close()


def test_newer_schema_is_refused(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "workspace.sqlite3")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(DatabaseVersionError):
        WorkspaceDatabase.load(tmp_path).connect()


def test_transaction_rolls_back_on_error(tmp_path: Path):
    db = WorkspaceDatabase.create(tmp_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction():
                db.connection.execute("INSERT INTO specs VALUES ('a', '{}')")
                # violates FOREIGN KEY (dep_id) REFERENCES specs
                db.connection.execute("INSERT INTO spec_deps VALUES ('a', 'missing')")
        assert db.connection.execute("SELECT COUNT(*) FROM specs").fetchone()[0] == 0
        assert not db.connection.in_transaction
    finally:
        db.close()


def test_transaction_rolls_back_on_keyboard_interrupt(tmp_path: Path):
    db = WorkspaceDatabase.create(tmp_path)
    try:
        with pytest.raises(KeyboardInterrupt):
            with db.transaction():
                db.connection.execute("INSERT INTO specs VALUES ('a', '{}')")
                raise KeyboardInterrupt
        assert db.connection.execute("SELECT COUNT(*) FROM specs").fetchone()[0] == 0
    finally:
        db.close()


def test_nested_transactions_join_outer(tmp_path: Path):
    db = WorkspaceDatabase.create(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            with db.transaction():
                db.connection.execute("INSERT INTO specs VALUES ('a', '{}')")
                with db.transaction():
                    db.connection.execute("INSERT INTO specs VALUES ('b', '{}')")
                raise RuntimeError
        assert db.connection.execute("SELECT COUNT(*) FROM specs").fetchone()[0] == 0
    finally:
        db.close()


def test_temp_table_does_not_leak_after_error(tmp_path: Path):
    db = WorkspaceDatabase.create(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            with db._temp_ids(["a", "b"]):
                raise RuntimeError
        # Previously: "table _ids already exists" on every later call.
        assert db.get_upstream_ids(["a"]) == set()
        assert db.get_downstream_ids(["a"]) == set()
    finally:
        db.close()


_LEGACY = {
    "iso_text_times": (
        "spec_id TEXT, spec_name TEXT, spec_fullname TEXT, file_root TEXT, file_path TEXT, "
        "session TEXT, status_state TEXT, status_category TEXT, status_status TEXT, "
        "status_reason TEXT, status_code INTEGER, started_on TEXT, finished_on TEXT, "
        "duration TEXT, workspace TEXT, measurements TEXT, PRIMARY KEY (spec_id, session)",
        "INSERT INTO results (spec_id, spec_name, session, status_state, status_category, "
        "status_status, status_reason, status_code, started_on, finished_on, duration, "
        "measurements) VALUES ('a', 't', 's1', 'COMPLETE', 'SKIP', 'SKIPPED', '', 0, "
        "'2025-01-01T00:00:00', 'NA', '5.0', '{}')",
        5.0,
    ),
    "real_times_status_state": (
        "spec_id TEXT, spec_name TEXT, spec_fullname TEXT, file_root TEXT, file_path TEXT, "
        "session TEXT, workspace TEXT, status_state TEXT, status_category TEXT, "
        "status_status TEXT, status_reason TEXT, status_code INTEGER, submitted REAL, "
        "started REAL, finished REAL, measurements TEXT, PRIMARY KEY (spec_id, session)",
        "INSERT INTO results (spec_id, spec_name, session, status_state, status_category, "
        "status_status, status_reason, status_code, submitted, started, finished, measurements) "
        "VALUES ('a', 't', 's1', 'COMPLETE', 'PASS', 'SUCCESS', '', 0, 1.0, 2.0, 3.0, '{}')",
        2.0,
    ),
    "real_times_job_state": (
        "spec_id TEXT, spec_name TEXT, spec_fullname TEXT, file_root TEXT, file_path TEXT, "
        "session TEXT, workspace TEXT, job_state TEXT, status_category TEXT, "
        "status_outcome TEXT, status_reason TEXT, status_code INTEGER, submitted REAL, "
        "started REAL, finished REAL, measurements TEXT, PRIMARY KEY (spec_id, session)",
        "INSERT INTO results (spec_id, spec_name, session, job_state, status_category, "
        "status_outcome, status_reason, status_code, submitted, started, finished, measurements) "
        "VALUES ('a', 't', 's1', 'RUNNING', 'NONE', 'NONE', '', -1, 1.0, 2.0, -1.0, '{}')",
        None,
    ),
}


@pytest.mark.parametrize("with_rows", [True, False])
@pytest.mark.parametrize("layout", sorted(_LEGACY))
def test_legacy_results_tables_are_migrated(tmp_path: Path, layout: str, with_rows: bool):
    ddl, insert, expected_total = _LEGACY[layout]
    conn = sqlite3.connect(tmp_path / "workspace.sqlite3")
    conn.execute(f"CREATE TABLE results ({ddl})")
    if with_rows:
        conn.execute(insert)
    conn.commit()
    conn.close()

    db = WorkspaceDatabase.load(tmp_path)
    try:
        db.connect()
        cols = [r[1] for r in db.connection.execute("PRAGMA table_info(results)")]
        assert list(cols) == list(dbmod.RESULTS_COLUMNS)
        assert _pragma(db, "user_version") == SCHEMA_VERSION
        # Previously failed with "no such column: job_state" for empty tables.
        db.reconcile_running_jobs("s1")
        results = db.get_results()
        if with_rows:
            r = results["a"]
            assert r["state"].phase.value == "DONE"
            if expected_total is not None:
                assert r["timekeeper"].total() == pytest.approx(expected_total)
        else:
            assert results == {}
    finally:
        db.close()
    # Re-opening a migrated database is a no-op.
    db = WorkspaceDatabase.load(tmp_path)
    db.connect()
    db.close()


def test_failed_migration_leaves_database_untouched(tmp_path: Path, monkeypatch):
    ddl, insert, _ = _LEGACY["real_times_status_state"]
    path = tmp_path / "workspace.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE results ({ddl})")
    conn.execute(insert)
    conn.commit()
    conn.close()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash during migration")

    monkeypatch.setattr(dbmod, "_legacy_timekeeper", boom)
    with pytest.raises(RuntimeError):
        WorkspaceDatabase.load(tmp_path).connect()

    conn = sqlite3.connect(path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(results)")]
    assert "status_state" in cols
    assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "results_new" not in tables
    conn.close()
