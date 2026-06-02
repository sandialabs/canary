import pytest

from _canary.workspace import NotAWorkspaceError
from _canary.workspace import Workspace
from _canary.workspace import WorkspaceExistsError


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


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
