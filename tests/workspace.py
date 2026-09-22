# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

import _canary.workspace as _workspace_module
from _canary.util.filesystem import working_dir
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


def test_view_settings_deserialize_ignores_unknown_keys():
    """ViewSettings.__deserialize__ must tolerate keys written by other canary
    versions (e.g. a legacy 'reports' field) instead of raising a TypeError."""
    from _canary.util import json_helper as json
    from _canary.view import ViewSettings

    blob = json.dumps(
        {
            "name": "TestResults",
            "when": "always",
            "only": "all",
            "mode": "symlink",
            # A field this version of ViewSettings does not know about.
            "reports": ["html", "json"],
            "__type__": "_canary.view::ViewSettings",
        }
    )
    settings = json.loads(blob)
    assert isinstance(settings, ViewSettings)
    assert settings.name == "TestResults"
    assert settings.when == "always"
    assert settings.only == "all"
    assert settings.mode == "symlink"
    assert not hasattr(settings, "reports")


def test_latest_view_survives_unknown_view_settings_key(tmp_path):
    """A view cache carrying an unknown ViewSettings key (written by a different
    canary version) must still load via Workspace.latest_view()."""
    import json as stdlib_json

    from _canary.view import ResultsView
    from _canary.view import ViewSettings

    proj = tmp_path / "project"
    proj.mkdir()
    ws = Workspace.create(proj)

    # Write a normal view cache, then inject an unknown key into the persisted
    # ViewSettings payload to emulate a cache from an incompatible version.
    ws.register_view(ResultsView(root=proj.parent, settings=ViewSettings()))
    cache = ws.cache_dir / "view"
    raw = stdlib_json.loads(cache.read_text())
    raw["settings"]["reports"] = ["html", "json"]
    cache.write_text(stdlib_json.dumps(raw, indent=2))

    loaded = ws.latest_view()
    assert loaded is not None
    assert isinstance(loaded.settings, ViewSettings)
    assert loaded.settings.name == "TestResults"


# --------------------------------------------------------------------------- #
# Portable plugin persistence in .canary/config.yaml (host/container mounts)   #
# --------------------------------------------------------------------------- #


def _create_with_plugins(anchor, plugins):
    """Create a workspace at *anchor* with config_mods carrying *plugins*."""
    import argparse

    from _canary import config

    with config.override():
        config._config.options = argparse.Namespace(config_mods={"plugins": list(plugins)})
        return Workspace.create(anchor)


def test_create_persists_plugin_path_relative_to_anchor(tmp_path):
    """A path-like plugin under the workspace tree is persisted RELATIVE to the
    anchor so the workspace is portable across absolute mount points."""
    import yaml

    proj = tmp_path / "run17"
    (proj / "analysis").mkdir(parents=True)
    (proj / "analysis" / "reverify.py").write_text("X = 1\n")

    # Pass the plugin as an ABSOLUTE path, as a host shell would.
    _create_with_plugins(proj, [str(proj / "analysis" / "reverify.py")])

    cfg = yaml.safe_load((proj / ".canary" / "config.yaml").read_text())
    assert cfg["canary"]["plugins"] == ["analysis/reverify.py"]


def test_create_keeps_module_name_plugin_verbatim(tmp_path):
    import yaml

    proj = tmp_path / "run17"
    proj.mkdir()
    _create_with_plugins(proj, ["mypkg.hooks"])

    cfg = yaml.safe_load((proj / ".canary" / "config.yaml").read_text())
    assert cfg["canary"]["plugins"] == ["mypkg.hooks"]


def test_persisted_relative_plugin_loads_after_tree_moved(tmp_path):
    """Emulate the /gpfs (host) vs /projects (container) mount mismatch: create a
    workspace under one prefix, move the whole tree to another, and confirm the
    persisted relative plugin still loads via Config.load()."""
    import argparse

    from _canary import config

    host = tmp_path / "gpfs" / "run17"
    (host / "analysis").mkdir(parents=True)
    (host / "analysis" / "hookmod.py").write_text(
        "import canary\n\n@canary.hookimpl\ndef canary_addoption(parser):\n    pass\n"
    )
    _create_with_plugins(host, [str(host / "analysis" / "hookmod.py")])

    # Relocate the entire tree to a different absolute prefix.
    container = tmp_path / "projects" / "run17"
    container.parent.mkdir(parents=True)
    host.rename(container)

    with config.override(), working_dir(container):
        config._config.options = argparse.Namespace()
        config._config.load()
        assert config._config.pluginmanager.get_plugin("hookmod") is not None


def test_stale_persisted_plugin_warns_and_does_not_crash(tmp_path, monkeypatch):
    """A stale/unresolvable plugin in .canary/config.yaml must degrade to a
    warning rather than raising and bricking every command in the workspace."""
    import argparse

    import _canary.config.config as _cfgmod
    from _canary import config

    proj = tmp_path / "run17"
    proj.mkdir()
    _create_with_plugins(proj, [])
    # Inject plugins that cannot possibly load (missing file + bogus module).
    (proj / ".canary" / "config.yaml").write_text(
        "canary:\n  plugins:\n  - analysis/missing.py\n  - totally.bogus.module\n"
    )

    warnings: list[str] = []
    monkeypatch.setattr(_cfgmod.logger, "warning", lambda msg, *a, **k: warnings.append(str(msg)))

    with config.override(), working_dir(proj):
        config._config.options = argparse.Namespace()
        # Must NOT raise even though every persisted plugin fails to load.
        config._config.load()

    joined = "\n".join(warnings)
    assert "analysis/missing.py" in joined
    assert "totally.bogus.module" in joined
