# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
import sys
from typing import Any

import pytest

import _canary.util.json_helper as json
from _canary import config
from _canary.app.pathspec import RequestBuilder
from _canary.app.pathspec import RequestNode
from _canary.app.pathspec import ScanPathsRequest
from _canary.config.argparsing import make_argument_parser
from _canary.config.config import Config


def assert_json_serializable(obj: Any) -> None:
    json.dumps(obj)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--debug"],
        ["-c", "debug:true"],
        ["-e", "SPAM=EGGS"],
        ["run", "--empty-ok"],
        ["run", "--style", "live=no"],
        ["find", "--files"],
        ["config", "show"],
        ["help"],
    ],
)
def test_parsed_core_command_options_are_snapshot_serializable(argv: list[str]) -> None:
    parser = make_argument_parser()
    parser.add_main_epilog(parser)

    config.pluginmanager.hook.canary_addcommand(parser=parser)
    config.pluginmanager.hook.canary_addoption(parser=parser)

    args = parser.parse_args(argv)

    with config.override():
        config.set_main_options(args)
        snapshot = config.snapshot()

    assert_json_serializable(snapshot)


def test_argparse_defaults_do_not_store_live_command_objects() -> None:
    """
    Regression test for accidentally putting command instances or other live
    Python objects into argparse defaults. Config snapshots must remain JSON
    serializable for child processes and schedulers.
    """
    parser = make_argument_parser()
    parser.add_main_epilog(parser)

    config.pluginmanager.hook.canary_addcommand(parser=parser)
    config.pluginmanager.hook.canary_addoption(parser=parser)

    args = parser.parse_args(["help"])

    bad: list[tuple[str, object]] = []

    for key, value in vars(args).items():
        if isinstance(value, (str, int, float, bool, type(None), list, tuple, dict, set)):
            continue
        if isinstance(value, argparse.Namespace):
            continue
        bad.append((key, value))

    assert not bad, f"Non-JSON-like argparse defaults found: {bad}"


def test_request_builder_json_helper_roundtrip():
    builder = RequestBuilder()
    builder.require_kind("scanpaths", "scanpaths")
    builder.scanpaths["/tmp/tests"] = ["a.pyt", "b.pyt"]

    text = json.dumps(builder)
    out = json.loads(text)

    assert isinstance(out, RequestBuilder)
    assert out.kind == "scanpaths"
    assert out.scanpaths == {"/tmp/tests": ["a.pyt", "b.pyt"]}


def test_request_node_json_helper_roundtrip():
    req = ScanPathsRequest(value={"/tmp/tests": ["a.pyt"]})

    text = json.dumps(req)
    out = json.loads(text)

    assert isinstance(out, RequestNode)
    assert out.kind == "scanpaths"
    assert out.value == {"/tmp/tests": ["a.pyt"]}


def test_run_cache_dir_config_default_is_none():
    assert config.get("run:cache:dir") is None


def test_run_cache_dir_config_settable():
    config.set("run:cache:dir", "/tmp/shared-canary-cache")
    assert config.get("run:cache:dir") == "/tmp/shared-canary-cache"


def test_find_cache_dir_prefers_env_then_config_then_workspace_tag(tmp_path, monkeypatch):
    from _canary.history.store import _find_cache_dir as find

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "WORKSPACE.TAG").write_text("")

    # 1. With nothing set, walk up to the WORKSPACE.TAG and use <ws>/cache.
    monkeypatch.delenv("CANARY_CACHE_DIR", raising=False)
    assert find(start=ws) == ws / "cache"

    # 2. A configured run:cache:dir takes precedence over the workspace tag.
    shared = tmp_path / "shared"
    config.set("run:cache:dir", str(shared))
    assert find(start=ws) == shared

    # 3. CANARY_CACHE_DIR wins over everything.
    envdir = tmp_path / "env"
    monkeypatch.setenv("CANARY_CACHE_DIR", str(envdir))
    assert find(start=ws) == envdir


def test_snapshot_captures_absolute_sys_path(tmp_path, monkeypatch):
    """The snapshot records sys.path so a consumer need not read config.yaml."""
    with config.override():
        config._config.invocation_dir = str(tmp_path)
        monkeypatch.syspath_prepend("relative/hooks")
        monkeypatch.syspath_prepend(str(tmp_path / "abs_hooks"))
        snapshot = config.snapshot()

    entries = snapshot["sys_path"]
    # Every recorded entry is absolute.
    assert all(os.path.isabs(p) for p in entries)
    # The relative entry was resolved against the invocation directory.
    assert os.path.join(str(tmp_path), "relative", "hooks") in entries
    assert str(tmp_path / "abs_hooks") in entries


def test_apply_snapshot_restores_missing_sys_path_entries(tmp_path, monkeypatch):
    """Applying a snapshot re-inserts its sys.path entries into the consumer."""
    new_entry = str(tmp_path / "plugin_dir")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != new_entry])
    assert new_entry not in sys.path

    snapshot = {
        "invocation_dir": str(tmp_path),
        "options": {},
        "data": {},
        "resource_manager": {},
        "sys_path": [new_entry],
    }
    cfg = Config(loadini=False)
    cfg._apply_snapshot(snapshot)

    assert new_entry in sys.path


def test_apply_snapshot_without_sys_path_key_is_noop(tmp_path):
    """A legacy snapshot lacking 'sys_path' still applies cleanly."""
    snapshot = {"invocation_dir": str(tmp_path), "options": {}, "data": {}, "resource_manager": {}}
    cfg = Config(loadini=False)
    cfg._apply_snapshot(snapshot)  # must not raise


def test_snapshot_plugin_load_warning_names_snapshot_source(tmp_path, caplog):
    with config.override() as cfg:
        cfg._consider_persisted_plugin("missing_plugin", base=tmp_path, source="config snapshot")

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "recorded in config snapshot" in text


def test_set_main_options_merges_session_plugins_into_effective_config(tmp_path):
    parser = make_argument_parser()
    args = parser.parse_args(["-p", str(tmp_path / "plugins" / "my_plugin.py")])

    with config.override() as cfg:
        cfg.invocation_dir = str(tmp_path)
        cfg.set_main_options(args)

        assert cfg.session_plugins == [{"name": "my_plugin", "path": str(tmp_path / "plugins")}]
        assert cfg.data["plugins"] == [{"name": "my_plugin", "path": str(tmp_path / "plugins")}]


def test_bootstrap_plugin_specs_include_env_and_cli(monkeypatch, tmp_path):
    from _canary.config.config import get_bootstrap_plugin_specs

    monkeypatch.setenv("CANARY_PLUGINS", f"env.plugin,{tmp_path / 'pkg'}")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("VALUE = 1\n")

    specs = get_bootstrap_plugin_specs(argv_plugins=[str(tmp_path / "plug.py")])

    assert specs == [
        {"name": "env.plugin"},
        {"name": "pkg", "path": str(tmp_path)},
        {"name": "plug", "path": str(tmp_path)},
    ]


def test_bootstrap_plugin_specs_append_autoloaded_canaryhooks(monkeypatch, tmp_path):
    from _canary.config.config import get_bootstrap_plugin_specs

    monkeypatch.chdir(tmp_path)
    (tmp_path / "canaryhooks.py").write_text("VALUE = 1\n")

    specs = get_bootstrap_plugin_specs(argv_plugins=[str(tmp_path / "plug.py")])

    assert specs == [
        {"name": "plug", "path": str(tmp_path)},
        {"name": "canaryhooks", "path": str(tmp_path)},
    ]


def test_bootstrap_plugin_specs_fall_back_to_importable_canaryhooks(monkeypatch, tmp_path):
    from _canary.config.config import get_bootstrap_plugin_specs

    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "canaryhooks.py").write_text("VALUE = 1\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(hooks_dir))

    specs = get_bootstrap_plugin_specs()

    assert specs == [{"name": "canaryhooks"}]


def test_set_main_options_appends_autoloaded_canaryhooks(tmp_path, monkeypatch):
    parser = make_argument_parser()
    args = parser.parse_args(["-p", str(tmp_path / "plugins" / "my_plugin.py")])
    (tmp_path / "canaryhooks.py").write_text("VALUE = 1\n")

    with config.override() as cfg:
        cfg.invocation_dir = str(tmp_path)
        monkeypatch.chdir(tmp_path)
        cfg.set_main_options(args)

        assert cfg.session_plugins == [
            {"name": "my_plugin", "path": str(tmp_path / "plugins")},
            {"name": "canaryhooks", "path": str(tmp_path)},
        ]
        assert cfg.data["plugins"] == [
            {"name": "my_plugin", "path": str(tmp_path / "plugins")},
            {"name": "canaryhooks", "path": str(tmp_path)},
        ]


def test_set_main_options_fall_back_to_importable_canaryhooks(tmp_path, monkeypatch):
    parser = make_argument_parser()
    args = parser.parse_args([])
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "canaryhooks.py").write_text("VALUE = 1\n")

    with config.override() as cfg:
        cfg.invocation_dir = str(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.syspath_prepend(str(hooks_dir))
        cfg.set_main_options(args)

        assert cfg.session_plugins == [{"name": "canaryhooks"}]
        assert cfg.data["plugins"] == [{"name": "canaryhooks"}]
