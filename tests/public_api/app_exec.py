# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""The ``app.exec_job`` application operation.

``canary exec`` runs a single job by spec id, bypassing the session scheduler.
The orchestration -- open the workspace, resolve the spec, build the job, check
readiness, run it, and persist the result -- lives in
:func:`_canary.app.exec_.exec_job`; the CLI only renders live status.  These
tests pin that contract and the observer seam the CLI depends on.
"""

from dataclasses import dataclass
from typing import Any

import pytest

import canary
from _canary import app

PYT_BODY = """\
import sys
def test():
    pass
if __name__ == "__main__":
    sys.exit(test())
"""


@dataclass
class _Request:
    kind: str
    value: Any


def _seed_workspace_with_one_spec(tmp_path):
    """Create a workspace with a single collected+run spec; return its id."""
    (tmp_path / "a.pyt").write_text(PYT_BODY)
    with canary.config.override():
        assert app.run(_Request(kind="scanpaths", value={str(tmp_path): []})) == 0
        (spec_id,) = app.get_results().keys()
    return spec_id


def test_exec_job_runs_single_spec_and_persists_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec_id = _seed_workspace_with_one_spec(tmp_path)

    with canary.config.override():
        job = app.exec_job(spec_id)
        assert job.status.is_success()

        # The freshly-run result must be persisted, not just held in memory.
        (record,) = app.get_results().values()
        assert record["status"].is_success()


def test_exec_job_observer_receives_lifecycle_events(tmp_path, monkeypatch):
    """The observer sees the job's lifecycle events with the job attached.

    This is the seam the CLI renders from; the app applies the phase
    transitions and forwards each event with the running job under ``"job"``.
    """
    monkeypatch.chdir(tmp_path)
    spec_id = _seed_workspace_with_one_spec(tmp_path)

    seen: list[str] = []

    def observer(event: dict) -> None:
        seen.append(event["event"])
        assert event["job"] is not None

    with canary.config.override():
        app.exec_job(spec_id, observer=observer)

    # A healthy job passes through submit -> stage -> start -> stop in order.
    for name in ("job_submitted", "job_staged", "job_started", "job_stopped"):
        assert name in seen
    assert seen.index("job_started") < seen.index("job_stopped")


def test_exec_job_unknown_spec_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_workspace_with_one_spec(tmp_path)

    with canary.config.override():
        with pytest.raises(ValueError, match="no matching spec"):
            app.exec_job("deadbeef")
