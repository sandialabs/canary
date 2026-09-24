# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The ``app.run`` application operation.

``canary run`` builds a request plus :class:`_canary.app.run.RunOptions` and
delegates the whole orchestration -- open/create the workspace, resolve the
request into a spec set, apply filters, pick the rerun strategy, execute -- to
:func:`_canary.app.run.run`.  These tests pin that contract so a future edit
cannot quietly move orchestration back into the CLI.
"""

from dataclasses import dataclass
from typing import Any

import canary
from _canary import app
from _canary.app.run import RunOptions

PYT_BODY = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


@dataclass
class _Request:
    """Minimal structural stand-in for a run request (kind + value)."""

    kind: str
    value: Any


def test_run_scanpaths_creates_workspace_and_executes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.pyt").write_text(PYT_BODY)

    with canary.config.override():
        request = _Request(kind="scanpaths", value={str(tmp_path): []})
        rc = app.run(request, RunOptions(work_tree=str(tmp_path)))

    assert rc == 0
    # The run must have created the workspace and persisted the spec it ran.
    with canary.config.override():
        reopened = app.open_workspace(tmp_path)
        assert {s.family for s in reopened.db.load_specs()} == {"a"}


def test_run_defaults_options_when_omitted(tmp_path, monkeypatch):
    """`app.run` accepts a bare request and supplies default RunOptions."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.pyt").write_text(PYT_BODY)

    with canary.config.override():
        rc = app.run(_Request(kind="scanpaths", value={str(tmp_path): []}))

    assert rc == 0


def test_wipe_requires_scanpaths(tmp_path, monkeypatch):
    """Wiping the workspace is only valid for scanpaths requests."""
    monkeypatch.chdir(tmp_path)

    with canary.config.override():
        try:
            app.run(_Request(kind="tag", value="smoke"), RunOptions(wipe_workspace=True))
        except RuntimeError:
            pass
        else:
            raise AssertionError("wipe with a non-scanpaths request must raise")
