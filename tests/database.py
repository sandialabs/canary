from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from typing import Generator
from typing import Protocol

import pytest

from _canary.database import NotASelection
from _canary.database import WorkspaceDatabase
from _canary.util.testing import generate_random_testcases
from _canary.util.testing import generate_random_testspecs

if TYPE_CHECKING:
    from _canary.testspec import ResolvedSpec


class MakeRandomSpecs(Protocol):
    def __call__(
        self, root: Path, count: int = 10, max_params: int = 3, max_rows: int = 5
    ) -> list["ResolvedSpec"]: ...


@pytest.fixture
def db(tmp_path: Path) -> Generator[WorkspaceDatabase, None, None]:
    f = tmp_path / "db.sqlite3"
    db = WorkspaceDatabase.create(f)
    yield db
    db.close()


@pytest.fixture
def make_random_specs():
    def factory(root: Path, count: int = 10, max_params: int = 3, max_rows: int = 5):
        return generate_random_testspecs(
            root, count=count, max_params=max_params, max_rows=max_rows
        )

    return factory


@pytest.fixture
def make_session():
    def factory(root: Path, count: int = 10, max_params: int = 3, max_rows: int = 5):
        cases = generate_random_testcases(
            root, count=count, max_params=max_params, max_rows=max_rows
        )
        for case in cases:
            with case.timekeeper.timeit():
                case.status.set(state="COMPLETE", category="PASS", status="SUCCESS")
        session = SimpleNamespace(name="session", cases=cases)
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

    for spec in specs:
        orig = {d.id for d in spec.dependencies}
        new = {d.id for d in loaded[spec.id].dependencies}
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

    for spec in specs:
        assert spec.id in graph


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
    db.put_results(session)
    results = db.get_results()
    for spec_id, result in results.items():
        assert result["id"] == spec_id
        assert result["status"] is not None
        assert result["timekeeper"] is not None
        assert result["measurements"] is not None


def test_result_history(db: WorkspaceDatabase, make_session):
    s1 = make_session(db.path.parent)
    s1.name = "s1"
    db.put_results(s1)

    s1.name = "s2"
    for case in s1.cases:
        with case.timekeeper.timeit():
            case.status.set(state="COMPLETE", category="PASS", status="SUCCESS")
    db.put_results(s1)

    spec_id = s1.cases[0].id
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
