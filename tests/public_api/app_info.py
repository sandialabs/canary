# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Workspace and tag info: the read queries ``canary info`` renders.

``canary info`` renders :meth:`Workspace.info` and :meth:`Workspace.tag_info`;
these tests pin the data they assemble.
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


def test_workspace_info_reports_specs_and_roots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)

        info = Workspace.load().info()

        assert str(tmp_path) in info["root"]
        assert len(info["specs"]) == 2


def test_tag_info_returns_metadata_and_unmasked_specs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("everything")

        info = Workspace.load().tag_info("everything")

        assert info["tag"] == "everything"
        assert {s.family for s in info["specs"]} == {"a", "b"}
        # created_on is lifted out of the metadata dict by tag_info.
        assert "created_on" not in info["metadata"]
        assert info["created_on"] is not None
