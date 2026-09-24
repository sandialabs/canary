# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Integration tests for the TUI over a real workspace.

Runs a tiny suite, then checks that the application query surface
(:mod:`_canary.app.queries`) and the TUI model/runner
(:mod:`_canary.tui`) present the persisted results.  The TUI is a read-only
adapter over ``canary.app``; these tests pin that contract end-to-end.
"""

import os

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


def test_job_log_query_returns_captured_output(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        jobs = queries.list_jobs()
        text = queries.job_log(jobs[0]["id"])
    # The pyt body runs cleanly; the captured stdout log exists and is a string.
    assert isinstance(text, str)


def test_model_open_selected_log_enters_log_mode(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.refresh()
        model.open_selected_log()
    assert model.state.mode == "log"
    assert model.state.log_lines  # never empty -- falls back to a placeholder
    assert model.state.selected is not None


def test_model_rerun_reexecutes_marked_jobs(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.refresh()
        ids = [j["id"] for j in model.state.jobs]
        rc = model.rerun(ids)
        assert rc == 0
        # The jobs still pass after the rerun.
        after = {j["id"]: j["status"] for j in queries.list_jobs()}
    assert all(after[i] == "PASS" for i in ids)


def test_edit_uses_vim_and_ignores_env(tmp_path, monkeypatch):
    """edit_file must launch vim, never $EDITOR/$VISUAL.

    Inside a full-screen TUI, $VISUAL/$EDITOR are often a GUI editor (e.g.
    ``code``) that detaches instead of blocking, so the TUI hardcodes vim
    (see ExplorerModel.EDITOR).
    """
    import subprocess

    # A GUI-ish editor is configured in the environment; it must NOT be used.
    monkeypatch.setenv("EDITOR", "code --wait")
    monkeypatch.setenv("VISUAL", "code --wait")

    target = tmp_path / "edit_me.pyt"
    target.write_text("original\n")
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        # Simulate the editor writing to the file with a later mtime (a real
        # editor session takes far longer than the clock resolution).
        target.write_text("original\nappended\n")
        st = target.stat()
        os.utime(target, (st.st_atime, st.st_mtime + 5))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    changed = tui.ExplorerModel().edit_file(str(target))

    assert changed is True
    # vim was launched with the file -- not "code --wait".
    assert calls == [["vim", str(target)]]


def test_edit_reports_no_change_when_file_untouched(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0))
    target = tmp_path / "untouched.pyt"
    target.write_text("original\n")

    assert tui.ExplorerModel().edit_file(str(target)) is False


def test_edit_is_noop_when_editor_not_found(tmp_path, monkeypatch):
    import subprocess

    def raise_not_found(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", raise_not_found)
    target = tmp_path / "x.pyt"
    target.write_text("original\n")

    assert tui.ExplorerModel().edit_file(str(target)) is False
