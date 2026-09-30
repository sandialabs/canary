# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The ``app.collect`` application operation.

``canary collect`` delegates entirely to :func:`_canary.app.collect`; this pins
that the operation opens the current workspace, discovers specs under the given
scan paths, persists them, and returns the resolved specs -- the same contract
``canary collect`` depends on.
"""

import canary
from _canary import app
from _canary.session.workspace import NotAWorkspaceError

PYT_BODY = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


def test_collect_returns_and_persists_resolved_specs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.pyt").write_text(PYT_BODY)
    (tmp_path / "b.pyt").write_text(PYT_BODY)

    with canary.config.override():
        app.create_workspace(tmp_path)
        specs = app.collect({str(tmp_path): []})

        assert {s.family for s in specs} == {"a", "b"}

        # The operation must persist, not merely resolve: a freshly opened
        # workspace sees the same specs.
        reopened = app.open_workspace(tmp_path)
        assert {s.family for s in reopened.db.load_specs()} == {"a", "b"}


def test_collect_without_workspace_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with canary.config.override():
        try:
            app.collect({str(tmp_path): []})
        except NotAWorkspaceError:
            pass
        else:
            raise AssertionError("collect must require an existing workspace")
