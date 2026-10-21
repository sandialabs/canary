# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Tests for the public run API adapter."""

from pathlib import Path

import pytest

import _canary.api.run as run_api


def test_run_request_scanpaths_accepts_string():
    request = run_api.RunRequest.scanpaths("examples")

    assert request.kind == "scanpaths"
    assert request.value == ["examples"]


def test_run_request_scanpaths_accepts_pathlike(tmp_path):
    path = tmp_path / "examples"

    request = run_api.RunRequest.scanpaths(path)

    assert request.kind == "scanpaths"
    assert request.value == [str(path)]


def test_run_request_scanpaths_accepts_iterable(tmp_path):
    paths = [tmp_path / "a", tmp_path / "b"]

    request = run_api.RunRequest.scanpaths(paths)

    assert request.kind == "scanpaths"
    assert request.value == [str(paths[0]), str(paths[1])]


def test_run_request_scanpaths_rejects_empty_iterable():
    with pytest.raises(ValueError, match="paths must contain at least one path"):
        run_api.RunRequest.scanpaths([])


def test_run_request_viewpaths_accepts_string():
    request = run_api.RunRequest.viewpaths("suite/test")

    assert request.kind == "viewpaths"
    assert request.value == ["suite/test"]


def test_run_request_viewpaths_accepts_iterable():
    request = run_api.RunRequest.viewpaths(["suite/a", "suite/b"])

    assert request.kind == "viewpaths"
    assert request.value == ["suite/a", "suite/b"]


def test_run_request_viewpaths_rejects_empty_iterable():
    with pytest.raises(ValueError, match="viewpaths must contain at least one prefix"):
        run_api.RunRequest.viewpaths([])


def test_run_request_specids_accepts_string():
    request = run_api.RunRequest.specids("abcdef123456")

    assert request.kind == "specids"
    assert request.value == ["abcdef123456"]


def test_run_request_specids_accepts_iterable():
    request = run_api.RunRequest.specids(["abc", "def"])

    assert request.kind == "specids"
    assert request.value == ["abc", "def"]


def test_run_request_specids_rejects_empty_iterable():
    with pytest.raises(ValueError, match="specids must contain at least one spec ID"):
        run_api.RunRequest.specids([])


def test_run_request_tag_accepts_nonempty_name():
    request = run_api.RunRequest.tag("nightly")

    assert request.kind == "tag"
    assert request.value == "nightly"


def test_run_request_tag_rejects_empty_name():
    with pytest.raises(ValueError, match="tag name must be non-empty"):
        run_api.RunRequest.tag("")


def test_make_request_from_paths():
    request = run_api.make_request(paths=["examples", "tests"])

    assert request.kind == "scanpaths"
    assert request.value == ["examples", "tests"]


def test_make_request_from_tag():
    request = run_api.make_request(from_tag="nightly")

    assert request.kind == "tag"
    assert request.value == "nightly"


def test_make_request_from_specids():
    request = run_api.make_request(specids=["abc", "def"])

    assert request.kind == "specids"
    assert request.value == ["abc", "def"]


def test_make_request_from_viewpaths():
    request = run_api.make_request(viewpaths=["root/a", "root/b"])

    assert request.kind == "viewpaths"
    assert request.value == ["root/a", "root/b"]


def test_make_request_defaults_to_configured_default_tag(monkeypatch):
    monkeypatch.setattr(
        run_api.config, "get", lambda key: "default-tag" if key == "run:default_tag" else None
    )

    request = run_api.make_request()

    assert request.kind == "tag"
    assert request.value == "default-tag"


def test_make_request_rejects_ambiguous_selectors():
    with pytest.raises(ValueError, match="run request is ambiguous"):
        run_api.make_request(paths="examples", from_tag="nightly")


def test_make_request_rejects_all_ambiguous_selector_names():
    with pytest.raises(ValueError) as excinfo:
        run_api.make_request(
            paths="examples", from_tag="nightly", specids="abc", viewpaths="root/a"
        )

    message = str(excinfo.value)
    assert "paths" in message
    assert "from_tag" in message
    assert "specids" in message
    assert "viewpaths" in message


def test_run_request_delegates_to_app_run(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 23

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    request = run_api.RunRequest.specids(["abc123"])
    options = run_api.RunOptions(only="all")

    rc = run_api.run_request(request, options)

    assert rc == 23
    assert captured["request"] is request
    assert captured["options"] is options


def test_run_builds_scanpaths_request_and_options(monkeypatch, tmp_path):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 7

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    work_tree = tmp_path / "workspace"

    rc = run_api.run(
        paths=Path("examples"),
        selection_tag="selected",
        on_options=["compiler=gcc", "build=debug"],
        keyword_exprs="not slow",
        parameter_expr="mesh=coarse",
        owners="tfuller",
        regex="converged",
        only="failed",
        wipe_workspace=True,
        work_tree=work_tree,
    )

    assert rc == 7

    request = captured["request"]
    assert request.kind == "scanpaths"
    assert request.value == ["examples"]

    options = captured["options"]
    assert isinstance(options, run_api.RunOptions)
    assert options.tag == "selected"
    assert options.on_options == ["compiler=gcc", "build=debug"]
    assert options.keyword_exprs == ["not slow"]
    assert options.parameter_expr == "mesh=coarse"
    assert options.owners == ["tfuller"]
    assert options.regex == "converged"
    assert options.only == "failed"
    assert options.wipe_workspace is True
    assert options.work_tree == str(work_tree)


def test_run_builds_tag_request_from_from_tag(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 0

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    rc = run_api.run(from_tag="nightly")

    assert rc == 0
    assert captured["request"].kind == "tag"
    assert captured["request"].value == "nightly"
    assert isinstance(captured["options"], run_api.RunOptions)


def test_run_builds_specids_request(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 0

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    rc = run_api.run(specids=["abc", "def"], keyword_exprs=["gpu", "not slow"])

    assert rc == 0
    assert captured["request"].kind == "specids"
    assert captured["request"].value == ["abc", "def"]
    assert captured["options"].keyword_exprs == ["gpu", "not slow"]


def test_run_builds_viewpaths_request(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 0

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    rc = run_api.run(viewpaths="suite/test")

    assert rc == 0
    assert captured["request"].kind == "viewpaths"
    assert captured["request"].value == ["suite/test"]


def test_run_uses_explicit_request(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 11

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    request = run_api.RunRequest.tag("nightly")

    rc = run_api.run(request=request, keyword_exprs="not slow", owners=["alice", "bob"])

    assert rc == 11
    assert captured["request"] is request
    assert captured["options"].keyword_exprs == ["not slow"]
    assert captured["options"].owners == ["alice", "bob"]


def test_run_defaults_to_configured_default_tag(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 0

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)
    monkeypatch.setattr(
        run_api.config, "get", lambda key: "default-tag" if key == "run:default_tag" else None
    )

    rc = run_api.run()

    assert rc == 0
    assert captured["request"].kind == "tag"
    assert captured["request"].value == "default-tag"


def test_run_rejects_ambiguous_selector_arguments():
    with pytest.raises(ValueError, match="run request is ambiguous"):
        run_api.run(paths="examples", specids="abc")


def test_string_options_are_promoted_to_single_item_lists(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 0

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    run_api.run(
        paths="examples", on_options="compiler=gcc", keyword_exprs="not slow", owners="tfuller"
    )

    options = captured["options"]
    assert options.on_options == ["compiler=gcc"]
    assert options.keyword_exprs == ["not slow"]
    assert options.owners == ["tfuller"]


def test_none_options_remain_none(monkeypatch):
    captured = {}

    def fake_app_run(request, options):
        captured["request"] = request
        captured["options"] = options
        return 0

    monkeypatch.setattr(run_api, "_app_run", fake_app_run)

    run_api.run(paths="examples")

    options = captured["options"]
    assert options.on_options is None
    assert options.keyword_exprs is None
    assert options.owners is None
    assert options.parameter_expr is None
    assert options.regex is None
    assert options.only is None
    assert options.view is None
    assert options.wipe_workspace is False
    assert options.work_tree is None


def test_noniterable_paths_raise_type_error():
    with pytest.raises(TypeError, match="paths must be a path or iterable of paths"):
        run_api.RunRequest.scanpaths(123)


def test_noniterable_string_list_argument_raises_type_error():
    with pytest.raises(TypeError, match="specids must be a string or iterable of strings"):
        run_api.RunRequest.specids(123)
