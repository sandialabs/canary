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


def test_job_view_file_path_is_absolute_and_exists(tmp_path):
    """file_path must be an absolute path to the real source file.

    It is stored split (file_root + a relative path) in the DB; the query
    surface joins them so an interface can open the file regardless of its CWD.
    The TUI's edit action broke when this was the bare relative path.
    """
    _make_workspace(tmp_path)
    # Query from a *different* CWD to prove the path is not CWD-relative.
    with working_dir(str(tmp_path / ".canary")), canary.config.override():
        jobs = queries.list_jobs()

    for j in jobs:
        p = j["file_path"]
        assert os.path.isabs(p), p
        assert os.path.exists(p), p
        assert os.path.basename(p) == "basic.pyt"


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


def test_model_refresh_log_follows_a_running_jobs_output(tmp_path):
    """While following, refresh_log re-reads the job's output and updates state."""
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.subscribe(queries.get_event_bus())
        model.refresh()
        model.state.set_viewport_height(5)

        # Drive the log source ourselves to simulate a growing output file.
        chunks = ["line 1\nline 2\n"]
        model.fetch_log = lambda spec_id, **k: chunks[-1]  # type: ignore[method-assign]

        sid = model.state.jobs[0]["id"]
        # Open following (as open_selected_log does while a run is active).
        model.state.open_log("job", chunks[0], spec_id=sid, follow=True)
        assert model.state.log_lines == ["line 1", "line 2"]

        # A follow tick picks up the appended line and re-pins to the tail.
        chunks.append("line 1\nline 2\nline 3\n")
        assert model.refresh_log() is True
        assert model.state.log_lines[-1] == "line 3"

        # No change -> no repaint.
        assert model.refresh_log() is False

        # Not following -> refresh_log is a no-op even if the source changed.
        model.state.log_follow = False
        chunks.append("line 1\nline 2\nline 3\nline 4\n")
        assert model.refresh_log() is False
        model.unsubscribe()


def test_model_rerun_reexecutes_marked_jobs(tmp_path):
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.subscribe(queries.get_event_bus())
        model.refresh()
        ids = [j["id"] for j in model.state.jobs]

        # In-place rerun: launches a child process that streams events back.
        assert model.begin_rerun(ids) is True
        assert model.run_active is True
        # A second rerun is refused while one is in flight.
        assert model.begin_rerun(ids) is False

        # Poll to completion (the child runs and exits; poll refreshes rows).
        import time

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if model.poll_run():
                break
            time.sleep(0.05)
        assert model.run_active is False

        after = {j["id"]: j["status"] for j in queries.list_jobs()}
        model.unsubscribe()
    assert all(after[i] == "PASS" for i in ids)


def test_model_cancel_run_terminates_child_and_clears_state(tmp_path):
    """Cancelling an in-flight run terminates the child and settles the model.

    Uses a fake run handle so the wiring is exercised without racing a real
    subprocess: begin a run, then cancel it, and assert the handle was
    terminated, the run is no longer active, and rows are refreshed.
    """

    class FakeHandle:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None  # still running until cancelled

        def terminate(self):
            self.terminated = True

    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        bus = queries.get_event_bus()
        model.subscribe(bus)
        model.refresh()

        # Observe job_cancelled events published on cancel.
        cancelled: list = []
        bus.subscribe(lambda e: cancelled.append(e), name="job_cancelled")

        handle = FakeHandle()
        model._launch = lambda *a, **k: handle  # type: ignore[method-assign]
        ids = [j["id"] for j in model.state.jobs]
        assert model.begin_rerun(ids) is True
        assert model.run_active is True

        # Feed a job_started so the progress tracker has an in-flight job to
        # announce as cancelled (the real child would emit this over the spool).
        from _canary.events import Event

        started_id = ids[0]
        bus.publish(Event("job_started", {"job": {"id": started_id, "qsize": len(ids)}}))

        # Cancel: the child is terminated and the model settles.
        assert model.cancel_run() is True
        assert handle.terminated is True
        assert model.run_active is False
        assert model.state.running is False
        # The in-flight job was announced as cancelled on the bus.
        assert [e.payload["job"]["id"] for e in cancelled] == [started_id]
        assert cancelled[0].payload["job"]["status"] == "CANCELLED"
        # Cancelling again is a safe no-op (no run, no new events).
        assert model.cancel_run() is False
        assert len(cancelled) == 1
        model.unsubscribe()


def test_model_begin_run_from_input_launches_a_run(tmp_path):
    """The ':' run prompt launches a run from a typed path, like canary run."""
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.subscribe(queries.get_event_bus())
        model.refresh()

        # A typed directory is classified into a scanpaths run and launched.
        started, message = model.begin_run_from_input(str(tmp_path))
        assert started is True, message
        assert message == ""
        assert model.run_active is True

        # A second run is refused while one is in flight.
        started2, message2 = model.begin_run_from_input(str(tmp_path))
        assert started2 is False
        assert "already in flight" in message2

        import time

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if model.poll_run():
                break
            time.sleep(0.05)
        assert model.run_active is False
        after = {j["name"]: j["status"] for j in queries.list_jobs()}
        model.unsubscribe()
    assert after == {"basic.x=1": "PASS", "basic.x=2": "PASS"}


def test_model_begin_run_from_input_reports_classification_error(tmp_path):
    """A bogus run-prompt line is rejected with a message, no run launched."""
    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.subscribe(queries.get_event_bus())
        model.refresh()
        started, message = model.begin_run_from_input("no-such-thing-xyz")
        assert started is False
        assert message  # a non-empty explanation
        assert model.run_active is False
        model.unsubscribe()


def test_tui_discovers_and_runs_paths_on_launch(tmp_path):
    """'canary tui PATH --once' discovers, runs, and then shows the results.

    This is the bridge that lets a run be started from the TUI: an initial
    scanpaths request creates the workspace and runs the tests before the
    explorer renders, all in one invocation.
    """
    from _canary.app.pathspec import ScanPathsRequest

    (tmp_path / "basic.pyt").write_text(PYT_BODY)
    with working_dir(str(tmp_path)), canary.config.override():
        # No workspace yet; the initial request must create and populate it.
        request = ScanPathsRequest(value={str(tmp_path): []})
        rc = tui.run(once=True, request=request)
        assert rc == 0
        jobs = {j["name"]: j["status"] for j in queries.list_jobs()}
    assert jobs == {"basic.x=1": "PASS", "basic.x=2": "PASS"}


def test_inplace_rerun_tracks_live_progress(tmp_path):
    """The live progress tracker reflects the run fed by the event stream."""
    import time

    _make_workspace(tmp_path)
    with working_dir(str(tmp_path)), canary.config.override():
        model = tui.ExplorerModel()
        model.subscribe(queries.get_event_bus())
        model.refresh()
        ids = [j["id"] for j in model.state.jobs]

        assert model.begin_rerun(ids) is True
        assert model.progress.snapshot().active is True

        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if model.poll_run():
                break
            time.sleep(0.05)

        snap = model.progress.snapshot()
        model.unsubscribe()

    # After completion the tracker is inactive, and it observed every job finish.
    assert snap.active is False
    assert snap.finished == len(ids)
    assert snap.by_status.get("PASS", 0) == len(ids)


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
