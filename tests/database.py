from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Generator
from typing import Protocol

import pytest

from _canary.database import NotASelection
from _canary.database import WorkspaceDatabase
from _canary.util.testing import generate_random_jobspecs
from _canary.util.testing import generate_random_testcases

if TYPE_CHECKING:
    from _canary.jobspec import JobSpec


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
        jobs = generate_random_testcases(
            root, count=count, max_params=max_params, max_rows=max_rows
        )
        for job in jobs:
            with job.timekeeper.timeit():
                job.status.set(category="PASS", outcome="SUCCESS")
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

    db.put_selection(
        tag="smoke",
        specs=specs[:2],
        scanpaths={"tests": ["a", "b"]},
        owners=["me"],
    )

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

    for job in session.jobs:
        with job.timekeeper.timeit():
            job.status.set(category="PASS", outcome="SUCCESS")
            job.workspace.session = "s2"
    db.put_results(*session.jobs)

    spec_id = session.jobs[0].id
    history = db.get_result_history(spec_id)
    assert len(history) == 2
    assert {history[0]["session"], history[1]["session"]} == {"s1", "s2"}


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
