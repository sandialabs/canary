# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Generator
from typing import Protocol

import pytest

from _canary.database import NotASelection
from _canary.database import WorkspaceDatabase
from _canary.util.testing import generate_random_jobs
from _canary.util.testing import generate_random_jobspecs

if TYPE_CHECKING:
    from _canary.core.jobspec import JobSpec


class MakeRandomSpecs(Protocol):
    def __call__(
        self, root: Path, count: int = 10, max_params: int = 3, max_rows: int = 5
    ) -> list["JobSpec"]: ...


@pytest.fixture
def db(tmp_path: Path) -> Generator[WorkspaceDatabase, None, None]:
    f = tmp_path / "db.sqlite3"
    db = WorkspaceDatabase.create(f)
    yield db
    db.close()


@pytest.fixture
def make_random_specs():
    def factory(root: Path, count: int = 10, max_params: int = 3, max_rows: int = 5):
        return generate_random_jobspecs(root, count=count, max_params=max_params, max_rows=max_rows)

    return factory


@pytest.fixture
def make_session():
    def factory(root: Path, count: int = 10, max_params: int = 3, max_rows: int = 5):
        jobs = generate_random_jobs(root, count=count, max_params=max_params, max_rows=max_rows)
        for i, job in enumerate(jobs):
            base = float(10 + i)
            job.timekeeper.open(at=base)
            job.timekeeper.stage(at=base + 0.1)
            job.timekeeper.start(at=base + 0.2)
            job.timekeeper.stop(at=base + 0.8)
            job.timekeeper.close(at=base + 1.0)
            job.status.set(category="PASS", outcome="SUCCESS")
            if job.workspace.session is None:
                job.workspace.session = "session"
        session = SimpleNamespace(name="session", jobs=jobs)
        return session

    return factory


def spec_ids(specs):
    return {s.id for s in specs}


def test_put_and_load_specs_roundtrip(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=5)

    db.put_specs(specs)
    loaded = db.load_specs()

    assert spec_ids(loaded) == spec_ids(specs)


def test_dependencies_roundtrip(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=6)

    db.put_specs(specs)
    loaded = {s.id: s for s in db.load_specs()}

    for s in specs:
        orig = {d.spec.id for d in s.dependencies}
        new = {d.spec.id for d in loaded[s.id].dependencies}
        assert orig == new


# -----------------------------------------------------------------------------
# Spec ID resolution
# -----------------------------------------------------------------------------


def test_resolve_unique_prefix(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=3)
    db.put_specs(specs)

    full = specs[0].id
    prefix = full[:6]

    assert db.resolve_spec_id(prefix) == full


def test_resolve_missing_prefix_returns_none(db: WorkspaceDatabase):
    assert db.resolve_spec_id("deadbeef") is None


# -----------------------------------------------------------------------------
# Dependency graph traversal
# -----------------------------------------------------------------------------


def xx_test_upstream_and_downstream(db: WorkspaceDatabase, make_linear_specs):
    """
    A -> B -> C
    """
    specs = make_linear_specs(3)
    db.put_specs(specs)

    A, B, C = specs

    downstream = db.get_downstream_ids([A.id])
    assert downstream == {B.id, C.id}

    upstream = db.get_upstream_ids([C.id])
    assert upstream == {A.id, B.id}


def test_get_dependency_graph_includes_all_nodes(
    db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs
):
    specs = make_random_specs(db.path.parent, count=5)
    db.put_specs(specs)

    graph = db.get_dependency_graph()

    for s in specs:
        assert s.id in graph


# -----------------------------------------------------------------------------
# Selections
# -----------------------------------------------------------------------------


def test_put_and_load_selection(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=4)
    db.put_specs(specs)

    db.put_selection(tag="smoke", specs=specs[:2], scanpaths={"tests": ["a", "b"]}, owners=["me"])

    meta = db.get_selection_metadata("smoke")
    assert meta["tag"] == "smoke"
    assert meta["scanpaths"] == {"tests": ["a", "b"]}

    loaded = db.load_specs_by_tagname("smoke")
    assert {s.id for s in loaded} == {s.id for s in specs[:2]}


def test_rename_selection(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=2)
    db.put_specs(specs)
    db.put_selection(tag="old", specs=specs, scanpaths={})

    db.rename_selection("old", "new")

    assert db.is_selection("new")
    assert not db.is_selection("old")


def test_missing_selection_raises(db: WorkspaceDatabase):
    with pytest.raises(NotASelection):
        db.get_selection_metadata("nope")


# -----------------------------------------------------------------------------
# Results
# -----------------------------------------------------------------------------


def test_put_and_get_results(db: WorkspaceDatabase, make_session):
    session = make_session(db.path.parent)
    db.put_results(*session.jobs)
    results = db.get_results()
    for spec_id, result in results.items():
        assert result["id"] == spec_id
        assert result["status"] is not None
        assert result["timekeeper"] is not None
        assert result["measurements"] is not None


def test_result_history(db: WorkspaceDatabase, make_session):
    session = make_session(db.path.parent)
    for job in session.jobs:
        job.workspace.session = "s1"
    db.put_results(*session.jobs)

    for i, job in enumerate(session.jobs):
        base = float(100 + i)
        job.timekeeper.open(at=base)
        job.timekeeper.stage(at=base + 0.1)
        job.timekeeper.start(at=base + 0.2)
        job.timekeeper.stop(at=base + 0.8)
        job.timekeeper.close(at=base + 1.0)
        job.status.set(category="PASS", outcome="SUCCESS")
        job.workspace.session = "s2"
    db.put_results(*session.jobs)

    spec_id = session.jobs[0].id
    history = db.get_result_history(spec_id)
    assert len(history) == 2
    assert {history[0]["session"], history[1]["session"]} == {"s1", "s2"}


def test_reconcile_running_jobs_flips_non_terminal_rows(db: WorkspaceDatabase, make_session):
    """Non-terminal (running/pending) rows are flipped to a terminal failure."""
    from _canary.core.job import JobPhase

    session = make_session(db.path.parent)
    # Simulate a mix: some jobs finished (DONE/SUCCESS), some left running/pending.
    running = session.jobs[: len(session.jobs) // 2]
    finished = session.jobs[len(session.jobs) // 2 :]
    for job in running:
        job.state.phase = JobPhase.RUNNING
        job.status.reset()
    for job in finished:
        job.state.phase = JobPhase.DONE
        job.status.set(category="PASS", outcome="SUCCESS")
    db.put_results(*session.jobs)

    n = db.reconcile_running_jobs("session")
    assert n == len(running)

    results = db.get_results()
    for job in running:
        r = results[job.id]
        assert r["state"].phase == JobPhase.DONE
        assert r["status"].outcome.name == "BROKEN"
        assert r["status"].category.value == "FAIL"
        assert r["status"].reason
    for job in finished:
        r = results[job.id]
        assert r["state"].phase == JobPhase.DONE
        assert r["status"].outcome.name == "SUCCESS"


def test_reconcile_running_jobs_noop_when_all_terminal(db: WorkspaceDatabase, make_session):
    """Reconciliation does nothing when every row is already terminal."""
    from _canary.core.job import JobPhase

    session = make_session(db.path.parent)
    for job in session.jobs:
        job.state.phase = JobPhase.DONE
        job.status.set(category="PASS", outcome="SUCCESS")
    db.put_results(*session.jobs)
    assert db.reconcile_running_jobs("session") == 0
    results = db.get_results()
    for job in session.jobs:
        assert results[job.id]["status"].outcome.name == "SUCCESS"


# -----------------------------------------------------------------------------
# View-based selection
# -----------------------------------------------------------------------------


def test_select_from_view_glob(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=5)
    db.put_specs(specs)
    # assume views look like "foo/bar/test.py"
    prefix = specs[0].file.parent.parent.as_posix() + "/%"
    ids = db.select_from_view([prefix])
    assert isinstance(ids, list)


# -----------------------------------------------------------------------------
# Foreign-key enforcement
#
# Foreign keys are only enforced when the connection sets ``PRAGMA
# foreign_keys=ON`` *and* the schema declares the constraints correctly.  These
# tests exercise the schema contract directly because that is the layer that
# regressed: a misspelled pragma plus a malformed constraint previously left
# these cascades silently disabled.
# -----------------------------------------------------------------------------


def test_deleting_spec_cascades_to_dependency_edges(db: WorkspaceDatabase):
    conn = db.connection
    conn.execute("INSERT INTO specs (spec_id, data) VALUES ('parent', '{}')")
    conn.execute("INSERT INTO specs (spec_id, data) VALUES ('dep', '{}')")
    conn.execute("INSERT INTO spec_deps (spec_id, dep_id) VALUES ('parent', 'dep')")

    conn.execute("DELETE FROM specs WHERE spec_id = 'parent'")

    remaining = conn.execute("SELECT spec_id, dep_id FROM spec_deps").fetchall()
    assert remaining == []


def test_deleting_depended_upon_spec_is_rejected(db: WorkspaceDatabase):
    import sqlite3

    conn = db.connection
    conn.execute("INSERT INTO specs (spec_id, data) VALUES ('parent', '{}')")
    conn.execute("INSERT INTO specs (spec_id, data) VALUES ('dep', '{}')")
    conn.execute("INSERT INTO spec_deps (spec_id, dep_id) VALUES ('parent', 'dep')")

    # 'dep' is referenced by the edge's dep_id (RESTRICT), so removing it while
    # a dependent edge exists would leave a dangling reference.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM specs WHERE spec_id = 'dep'")


def test_deleting_spec_cascades_to_selection(db: WorkspaceDatabase):
    conn = db.connection
    conn.execute("INSERT INTO specs (spec_id, data) VALUES ('s1', '{}')")
    conn.execute("INSERT INTO selections (tag, spec_id) VALUES ('smoke', 's1')")

    conn.execute("DELETE FROM specs WHERE spec_id = 's1'")

    remaining = conn.execute("SELECT tag, spec_id FROM selections").fetchall()
    assert remaining == []


# -----------------------------------------------------------------------------
# Read-only query surface (schema / stats / select)
# -----------------------------------------------------------------------------


def test_select_rejects_non_select_statements(db: WorkspaceDatabase):
    for statement in (
        "DELETE FROM specs",
        "DROP TABLE specs",
        "INSERT INTO specs VALUES ('x','{}')",
    ):
        with pytest.raises(ValueError):
            db.select(statement)


def test_select_returns_rows_as_dicts(db: WorkspaceDatabase, make_random_specs: MakeRandomSpecs):
    specs = make_random_specs(db.path.parent, count=3)
    db.put_specs(specs)

    rows = db.select("SELECT spec_id FROM specs ORDER BY spec_id")

    assert {row["spec_id"] for row in rows} == spec_ids(specs)


def test_schema_reports_table_definitions(db: WorkspaceDatabase):
    schema = db.get_schema()

    assert {"specs", "spec_deps", "selections", "results"} <= set(schema)
    assert schema["specs"].strip().upper().startswith("CREATE TABLE")


def test_results_for_session_filters_by_session(db: WorkspaceDatabase, make_session):
    session = make_session(db.path.parent)
    for job in session.jobs:
        job.workspace.session = "s1"
    db.put_results(*session.jobs)

    rows = db.get_results_for_session("s1")

    assert {row["id"] for row in rows} == {job.id for job in session.jobs}
    assert db.get_results_for_session("does-not-exist") == []


def test_stats_reports_latest_session_outcomes(db: WorkspaceDatabase, make_session):
    session = make_session(db.path.parent)
    for job in session.jobs:
        job.workspace.session = "s1"
    db.put_specs([job.spec for job in session.jobs])
    db.put_results(*session.jobs)

    stats = db.get_stats()

    assert stats["spec_count"] == len(session.jobs)
    assert stats["session_count"] == 1
    assert stats["latest_session"] == "s1"
    # make_session sets every job to SUCCESS, so the latest-session histogram
    # must attribute all specs to a single outcome bucket.
    assert sum(stats["outcomes"].values()) == len(session.jobs)
