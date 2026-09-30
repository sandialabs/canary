# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The workspace/tag info application operations.

``canary info`` renders the data returned by ``app.get_workspace_info`` and
``app.get_tag_info``; these tests pin that the facade returns the assembled data
(so the subcommand no longer reaches into ``workspace.db``).
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


def test_workspace_info_reports_specs_and_roots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)

        info = app.get_workspace_info()

        assert str(tmp_path) in info["root"]
        assert len(info["specs"]) == 2


def test_tag_info_returns_metadata_and_unmasked_specs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        _seed_workspace(tmp_path)
        app.select("everything")

        info = app.get_tag_info("everything")

        assert info["tag"] == "everything"
        assert {s.family for s in info["specs"]} == {"a", "b"}
        # created_on is lifted out of the metadata dict by the facade.
        assert "created_on" not in info["metadata"]
        assert info["created_on"] is not None
