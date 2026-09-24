# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Integration tests for the TUI over a real workspace.

Runs a tiny suite, then checks that the application query surface
(:mod:`_canary.app.queries`) and the TUI model/runner
(:mod:`_canary.tui`) present the persisted results.  The TUI is a read-only
adapter over ``canary.app``; these tests pin that contract end-to-end.
"""

import canary
from _canary import tui
from _canary.app import queries
from _canary.util.filesystem import working_dir
from _canary.util.testing import CanaryCommand

PYT_BODY = """\
import sys
import canary
import canary_pyt
canary_pyt.directives.parameterize("x", (1, 2))

def test():
    canary.get_instance()
    return 0

if __name__ == "__main__":
    sys.exit(test())
"""


def _make_workspace(tmp_path):
    (tmp_path / "basic.pyt").write_text(PYT_BODY)
    with working_dir(str(tmp_path)):
        run = CanaryCommand("run")
        cp = run("-w", ".")
    assert cp.returncode == 0


def test_list_jobs_projects_results(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        jobs = queries.list_jobs()

    assert {j["name"] for j in jobs} == {"basic.x=1", "basic.x=2"}
    for j in jobs:
        assert j["status"] == "PASS"
        assert j["phase"] == "DONE"
        assert j["duration"] >= 0.0
        # projection is primitives only -- no _canary types leak out
        assert isinstance(j["status_label"], str)
        assert isinstance(j["duration"], float)


def test_workspace_summary_and_counts(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        summary = queries.workspace_summary()
        jobs = queries.list_jobs()
        counts = queries.status_counts(jobs)

    assert summary["spec_count"] == 2
    assert summary["session_count"] >= 1
    assert counts == {"PASS": 2}


def test_job_history_returns_views(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        jobs = queries.list_jobs()
        history = queries.job_history(jobs[0]["id"])

    assert history
    assert all(h["id"] == jobs[0]["id"] for h in history)


def test_explorer_model_refresh_populates_state(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.refresh()

    assert len(model.state.jobs) == 2
    assert model.state.selected is not None
    # filter/navigation work against real data
    model.state.set_filter("PASS")
    assert len(model.state.visible_jobs) == 2


def test_tui_run_once_is_noninteractive_and_returns_zero(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        rc = tui.run(once=True)
    assert rc == 0


def test_public_app_exposes_query_surface():
    for name in ("list_jobs", "job_history", "workspace_summary", "status_counts"):
        assert hasattr(canary.app, name)


def test_model_marks_dirty_on_bus_event():
    """A job event flips the model's dirty flag so the runner refreshes promptly."""
    from _canary.events import EventBus

    bus = EventBus()
    model = tui.ExplorerModel()
    model.subscribe(bus)
    try:
        assert model.consume_dirty() is False  # nothing yet
        bus.emit("job_started")
        assert model.consume_dirty() is True  # event observed
        assert model.consume_dirty() is False  # flag cleared (edge-triggered)
    finally:
        model.unsubscribe()


def test_model_unsubscribe_stops_marking_dirty():
    from _canary.events import EventBus

    bus = EventBus()
    model = tui.ExplorerModel()
    model.subscribe(bus)
    model.unsubscribe()
    bus.emit("job_finished")
    assert model.consume_dirty() is False
