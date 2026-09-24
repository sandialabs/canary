# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The selection application operations.

``canary select`` and ``canary selection`` delegate their selection lifecycle
(create from all specs, create from another tag, rename, delete, existence
check) to the ``_canary.app`` facade.  These tests pin that contract so the
subcommands stay thin adapters.
"""

import canary
from _canary import app

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
    app.create_workspace(tmp_path)
    app.collect({str(tmp_path): []})


def test_select_creates_tag_from_all_specs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)

        specs = app.select("everything")

        assert {s.family for s in specs} == {"a", "b"}
        assert app.is_selection("everything")


def test_select_from_tag_filters_source_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("everything")

        subset = app.select("just_a", from_tag="everything", keyword_exprs=["a"])

        assert {s.family for s in subset} == {"a"}
        assert app.is_selection("just_a")


def test_rename_selection_moves_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("old")

        app.rename_selection("old", "new")

        assert app.is_selection("new")
        assert not app.is_selection("old")


def test_delete_selection_removes_tag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("temp")

        app.delete_selection("temp")

        assert not app.is_selection("temp")
