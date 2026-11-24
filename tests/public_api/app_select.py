# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Selection lifecycle: ``app.select`` plus the Workspace selection queries.

``canary select`` and ``canary selection`` create selections through
:func:`_canary.app.select` (from all specs or from another tag) and check,
rename and delete them through the workspace (``is_tag``, ``db``).  These tests
pin that lifecycle.
"""

import canary
from _canary import app
from _canary.engine.engine import Engine
from _canary.workspace.workspace import Workspace

PYT_BODY = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


def _seed_workspace(tmp_path):
    (tmp_path / "a.pyt").write_text(PYT_BODY)
    (tmp_path / "b.pyt").write_text(PYT_BODY)
    Workspace.create(tmp_path)
    Engine(Workspace.load()).collect({str(tmp_path): []})


def test_select_creates_tag_from_all_specs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)

        specs = app.select("everything")

        assert {s.family for s in specs} == {"a", "b"}
        assert Workspace.load().is_tag("everything")


def test_select_from_tag_filters_source_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("everything")

        subset = app.select("just_a", from_tag="everything", keyword_exprs=["a"])

        assert {s.family for s in subset} == {"a"}
        assert Workspace.load().is_tag("just_a")


def test_rename_selection_moves_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("old")

        Workspace.load().db.rename_selection("old", "new")

        assert Workspace.load().is_tag("new")
        assert not Workspace.load().is_tag("old")


def test_delete_selection_removes_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("temp")

        Workspace.load().db.delete_selection("temp")

        assert not Workspace.load().is_tag("temp")


def test_select_from_root_accepts_paths_relative_to_the_cwd(tmp_path, monkeypatch):
    """Regression: a relative root never matched, since spec files are absolute."""
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        (tmp_path / "x").mkdir()
        (tmp_path / "y").mkdir()
        (tmp_path / "x" / "a.pyt").write_text(PYT_BODY)
        (tmp_path / "y" / "b.pyt").write_text(PYT_BODY)
        Workspace.create(tmp_path)
        Engine(Workspace.load()).collect({str(tmp_path): []})

        relative = app.select("rel", prefixes=["x"])
        absolute = app.select("abs", prefixes=[str(tmp_path / "x")])

        assert {s.family for s in relative} == {s.family for s in absolute} == {"a"}
        monkeypatch.chdir(tmp_path / "x")
        assert {s.family for s in app.select("here", prefixes=["."])} == {"a"}
