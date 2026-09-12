# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.workspace as _workspace_module
from _canary.workspace import NotAWorkspaceError
from _canary.workspace import Workspace
from _canary.workspace import WorkspaceExistsError
from _canary.workspace import set_workspace_dir


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def reset_workspace_override():
    """Ensure _override_workspace_dir is cleared between tests."""
    _workspace_module._override_workspace_dir = None
    yield
    _workspace_module._override_workspace_dir = None


def test_create_and_load_workspace(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()

    ws = Workspace.create(root)
    assert (ws.root / "WORKSPACE.TAG").exists()
    assert (ws.root / "VERSION").exists()
    assert ws.refs_dir.exists()
    assert ws.sessions_dir.exists()
    assert ws.cache_dir.exists()
    assert ws.tmp_dir.exists()
    assert ws.logs_dir.exists()
    assert (ws.root / "workspace.sqlite3").exists()

    ws2 = Workspace.load(root)
    assert ws2.root == ws.root
    assert ws2.sessions_dir == ws.sessions_dir


def test_create_twice_raises(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    Workspace.create(root)
    with pytest.raises(WorkspaceExistsError):
        Workspace.create(root)


def test_find_anchor_none(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    assert Workspace.find_anchor(root) is None


def test_find_anchor_when_in_child_dir(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    Workspace.create(root)

    child = root / "a" / "b"
    child.mkdir(parents=True)

    assert Workspace.find_anchor(child) == root


def test_find_anchor_when_start_is_canary_dir(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    ws = Workspace.create(root)

    assert Workspace.find_anchor(ws.root) == root  # passing ".canary" dir


def test_find_workspace_returns_path(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    ws = Workspace.create(root)

    assert Workspace.find_workspace(root) == ws.root


def test_load_raises_when_not_workspace(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    with pytest.raises(NotAWorkspaceError):
        Workspace.load(root)


def test_remove_no_workspace_returns_none(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    assert Workspace.remove(root) is None


def test_remove_workspace_without_view(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    ws = Workspace.create(root)

    removed = Workspace.remove(root)
    assert removed == ws.root
    assert not ws.root.exists()


def test_relative_to_view_none_when_no_view(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    ws = Workspace.create(root)

    assert ws.relative_to_view(root / "anything") is None


def test_is_session_dir(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    ws = Workspace.create(root)

    some_session = ws.sessions_dir / "abc"
    some_session.mkdir(parents=True)
    assert ws.is_session_dir(some_session) is True
    assert ws.is_session_dir(root / "not_sessions") is False


def test_info_contains_expected_fields(chdir_tmp):
    root = chdir_tmp / "proj"
    root.mkdir()
    ws = Workspace.create(root)

    info = ws.info()
    assert "root" in info
    assert "session_count" in info
    assert "latest_session" in info
    assert "tags" in info
    assert "specs" in info
    assert "version" in info
    assert "workspace_version" in info
    assert info["root"] == str(ws.root)


# ---------------------------------------------------------------------------
# --canary-dir / CANARY_DIR / set_workspace_dir
# ---------------------------------------------------------------------------


def test_set_workspace_dir_loads_from_explicit_path(tmp_path):
    """set_workspace_dir() lets Workspace.load() find a workspace not on cwd path."""
    proj = tmp_path / "project"
    proj.mkdir()
    ws = Workspace.create(proj)

    # Working directory has no workspace.
    other = tmp_path / "other"
    other.mkdir()

    set_workspace_dir(ws.root)
    ws2 = Workspace.load()  # no start= arg, cwd is irrelevant
    assert ws2.root == ws.root


def test_set_workspace_dir_rejects_non_workspace(tmp_path):
    """set_workspace_dir() raises NotAWorkspaceError for a plain directory."""
    plain = tmp_path / "notaworkspace"
    plain.mkdir()
    with pytest.raises(NotAWorkspaceError):
        set_workspace_dir(plain)


def test_set_workspace_dir_override_supersedes_cwd(tmp_path, monkeypatch):
    """Override takes precedence even when a different workspace exists on the cwd path."""
    proj_a = tmp_path / "proj_a"
    proj_a.mkdir()
    ws_a = Workspace.create(proj_a)

    proj_b = tmp_path / "proj_b"
    proj_b.mkdir()
    ws_b = Workspace.create(proj_b)

    # Stand inside proj_a so cwd discovery would find ws_a.
    monkeypatch.chdir(proj_a)

    set_workspace_dir(ws_b.root)
    ws = Workspace.load()
    assert ws.root == ws_b.root


def test_canary_dir_env_var(tmp_path, monkeypatch):
    """CANARY_DIR env var is honoured by CanaryMain.__enter__ → set_workspace_dir."""
    proj = tmp_path / "project"
    proj.mkdir()
    ws = Workspace.create(proj)

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("CANARY_DIR", str(ws.root))

    from _canary.main import CanaryMain

    with CanaryMain([]):
        ws2 = Workspace.load()
        assert ws2.root == ws.root


def test_canary_dir_cli_flag(tmp_path, monkeypatch):
    """--canary-dir CLI flag is pre-parsed and calls set_workspace_dir."""
    proj = tmp_path / "project"
    proj.mkdir()
    ws = Workspace.create(proj)

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)

    from _canary.main import CanaryMain

    with CanaryMain(["--canary-dir", str(ws.root)]):
        ws2 = Workspace.load()
        assert ws2.root == ws.root


def test_canary_dir_flag_eq_form(tmp_path, monkeypatch):
    """--canary-dir=<path> (equals form) is also accepted."""
    proj = tmp_path / "project"
    proj.mkdir()
    ws = Workspace.create(proj)

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)

    from _canary.main import CanaryMain

    with CanaryMain([f"--canary-dir={ws.root}"]):
        ws2 = Workspace.load()
        assert ws2.root == ws.root


# ---------------------------------------------------------------------------
# cache/view stale-root fix
# ---------------------------------------------------------------------------


def test_latest_view_root_is_recomputed_from_live_workspace(tmp_path):
    """latest_view() returns a ResultsView with root=workspace.root.parent
    even when the cache/view file was written with a different (stale) root."""
    from _canary.view import ResultsView
    from _canary.view import ViewSettings

    proj = tmp_path / "project"
    proj.mkdir()
    ws = Workspace.create(proj)

    settings = ViewSettings()
    # Write a view with a deliberately wrong root.
    stale_root = tmp_path / "stale_location"
    stale_view = ResultsView(root=stale_root, settings=settings)
    ws.register_view(stale_view)

    # latest_view() must correct the root to the live anchor, ignoring the cache.
    loaded = ws.latest_view()
    assert loaded is not None
    assert loaded.root == ws.root.parent
    assert loaded.settings.name == settings.name


def test_results_view_serialize_omits_root(tmp_path):
    """ResultsView.__serialize__ must not include 'root' (it is recomputed at load)."""
    from _canary.util import json_helper as json
    from _canary.view import ResultsView
    from _canary.view import ViewSettings

    view = ResultsView(root=tmp_path, settings=ViewSettings())
    blob = json.dumps(view)
    import json as stdlib_json

    d = stdlib_json.loads(blob)
    assert "root" not in d, "root must not be persisted in the serialized view"
