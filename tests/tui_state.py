# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Pure-logic tests for the TUI state machine and renderer.

These exercise :mod:`_canary.tui.state` and :mod:`_canary.tui.render` without a
workspace or a terminal, using hand-built ``JobView`` rows.  They pin the
navigation, filtering, and detail behaviour the runner and any future
interface rely on.
"""

from rich.console import Console

from _canary.tui.render import render_frame
from _canary.tui.render import render_table
from _canary.tui.state import ExplorerState


def _summary(root="/ws/.canary"):
    return {
        "root": root,
        "session_count": 1,
        "latest_session": "2026-01-01T00-00-00",
        "spec_count": 3,
        "tags": [],
        "version": "0.0.0",
    }


def _view(name, status, *, id=None, duration=0.0, phase="DONE"):
    sid = id or (name + "0000000")
    return {
        "id": sid,
        "short_id": sid[:8],
        "name": name,
        "fullname": name + ".fullname",
        "file_path": f"/tests/{name}.pyt",
        "phase": phase,
        "status": status,
        "status_label": f"{status} (X)",
        "status_markup": f"[green]{status} (X)[/]",
        "status_glyph": "*",
        "category": status,
        "outcome": "SUCCESS",
        "reason": "" if status == "PASS" else "boom",
        "duration": duration,
        "session": "2026-01-01T00-00-00",
    }


def _rows():
    return [
        _view("a", "PASS", id="aaaaaaaa1"),
        _view("b", "FAIL", id="bbbbbbbb2"),
        _view("c", "PASS", id="cccccccc3"),
    ]


def test_cursor_movement_is_clamped():
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.cursor == 0
    st.move(-1)
    assert st.cursor == 0  # clamped at top
    st.move(1)
    assert st.cursor == 1
    st.move(100)
    assert st.cursor == 2  # clamped at bottom
    st.move_home()
    assert st.cursor == 0
    st.move_end()
    assert st.cursor == 2


def test_selection_tracks_spec_id_across_refresh():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.move_end()
    assert st.selected_id == "cccccccc3"
    # A refresh that reorders/adds rows should keep the same job selected.
    reordered = list(reversed(_rows()))
    st.update_jobs(reordered)
    assert st.selected_id == "cccccccc3"


def test_status_filter_and_cycle():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.set_filter("PASS")
    assert [j["name"] for j in st.visible_jobs] == ["a", "c"]
    st.set_filter("FAIL")
    assert [j["name"] for j in st.visible_jobs] == ["b"]
    st.set_filter(None)
    assert len(st.visible_jobs) == 3
    # cycling: None -> FAIL -> PASS -> None (statuses sorted: FAIL, PASS)
    st._cycle_filter()
    assert st.status_filter == "FAIL"
    st._cycle_filter()
    assert st.status_filter == "PASS"
    st._cycle_filter()
    assert st.status_filter is None


def test_handle_key_quit_and_detail_toggle():
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.show_detail is False
    assert st.handle_key("d") is True
    assert st.show_detail is True
    assert st.handle_key("d") is True
    assert st.show_detail is False
    assert st.handle_key("q") is True
    assert st.quit is True


def test_enter_requests_log_not_detail():
    """Enter opens the log (I/O the runner performs); it must not toggle detail."""
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.wants_log("enter") is True
    st.handle_key("enter")
    # State stays in list mode until the runner supplies the log text.
    assert st.mode == "list"
    assert st.show_detail is False


def test_log_mode_scroll_and_return():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.set_viewport_height(3)
    st.open_log("a", "l1\nl2\nl3\nl4\nl5\nl6")
    assert st.mode == "log" and st.log_top == 0
    st.handle_key("j")
    assert st.log_top == 1  # scrolled down one line
    st.handle_key("G")
    assert st.log_top == max(0, 6 - 3)  # clamped to last page
    st.handle_key("g")
    assert st.log_top == 0
    st.handle_key("q")
    assert st.mode == "list"  # q returns to the list, does not quit
    assert st.quit is False


def test_log_follow_pins_to_tail_and_updates():
    st = ExplorerState()
    st.set_viewport_height(3)
    st.open_log("job", "l1\nl2\nl3\nl4", spec_id="abc", follow=True)
    # Following opens pinned to the bottom.
    assert st.log_follow is True
    assert st.log_spec_id == "abc"
    assert st.log_top == max(0, 4 - 3)
    # New output arrives; the view re-pins to the new tail.
    assert st.update_log("l1\nl2\nl3\nl4\nl5\nl6") is True
    assert st.log_top == max(0, 6 - 3)
    # Identical text is a no-op (no needless repaint).
    assert st.update_log("l1\nl2\nl3\nl4\nl5\nl6") is False


def test_log_scroll_up_stops_following_then_G_resumes():
    st = ExplorerState()
    st.set_viewport_height(3)
    st.open_log("job", "\n".join(f"l{i}" for i in range(10)), spec_id="abc", follow=True)
    assert st.log_follow is True
    st.handle_key("k")  # scroll up -> stop following, freeze the view
    assert st.log_follow is False
    top_after_scroll = st.log_top
    # A refresh while frozen must not yank the view to the bottom.
    st.update_log("\n".join(f"l{i}" for i in range(20)))
    assert st.log_top == top_after_scroll
    # G jumps to the bottom and resumes following.
    st.handle_key("G")
    assert st.log_follow is True
    assert st.log_top == max(0, 20 - 3)


def test_log_f_toggles_follow():
    st = ExplorerState()
    st.set_viewport_height(3)
    st.open_log("job", "l1\nl2\nl3\nl4\nl5", spec_id="abc", follow=False)
    assert st.log_follow is False
    st.handle_key("f")
    assert st.log_follow is True
    assert st.log_top == max(0, 5 - 3)  # enabling jumps to the tail
    st.handle_key("f")
    assert st.log_follow is False


def test_close_log_clears_follow_state():
    st = ExplorerState()
    st.open_log("job", "l1\nl2", spec_id="abc", follow=True)
    st.close_log()
    assert st.mode == "list"
    assert st.log_spec_id is None
    assert st.log_follow is False


def test_viewport_windowing_keeps_cursor_visible():
    st = ExplorerState()
    st.update_jobs([_view(f"j{i}", "PASS", id=f"{i:09d}") for i in range(30)])
    st.set_viewport_height(5)
    assert len(st.window()) == 5
    assert st.window()[0]["name"] == "j0"  # rows kept in the given order
    st.move_end()
    # The window has scrolled so the last (selected) row is visible.
    assert st.window()[-1]["name"] == "j29"
    assert 0 <= st.window_cursor < 5


def test_mark_toggles_and_advances():
    st = ExplorerState()
    st.update_jobs(_rows())  # a (PASS), b (FAIL), c (PASS)
    st.handle_key("x")  # mark a, advance to b
    assert st.marked_ids == {"aaaaaaaa1"}
    assert st.cursor == 1
    st.handle_key("x")  # mark b, advance to c
    assert st.marked_ids == {"aaaaaaaa1", "bbbbbbbb2"}
    st.move_home()
    st.handle_key("x")  # unmark a
    assert st.marked_ids == {"bbbbbbbb2"}


def test_marks_survive_refresh_and_prune_missing():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.handle_key("x")  # mark a
    st.move(1)
    st.handle_key("x")  # mark b
    # A refresh that drops 'b' should keep 'a' marked and forget the absent 'b'.
    st.update_jobs([_view("a", "PASS", id="aaaaaaaa1")])
    assert st.rerun_target_ids() == ["aaaaaaaa1"]


def test_clear_marks():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.handle_key("x")
    assert st.marked_ids
    st.handle_key("c")
    assert st.marked_ids == set()


def test_rerun_targets_cursor_when_nothing_marked():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.move_end()  # cursor on c
    assert st.marked_ids == set()
    assert st.rerun_target_ids() == ["cccccccc3"]


def test_rerun_request_is_edge_triggered():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.handle_key("x")  # mark a
    assert st.handle_key("r") is True
    assert st.consume_rerun_request() == ["aaaaaaaa1"]
    # Consumed once; a second consume yields nothing until requested again.
    assert st.consume_rerun_request() == []


def test_rerun_key_ignored_when_no_target():
    st = ExplorerState()  # empty view
    assert st.handle_key("r") is False
    assert st.consume_rerun_request() == []


def test_edit_request_returns_cursor_file_path():
    st = ExplorerState()
    st.update_jobs(_rows())  # each _view has file_path /tests/<name>.pyt
    assert st.handle_key("e") is True
    assert st.consume_edit_request() == "/tests/a.pyt"
    # Edge-triggered: consumed once.
    assert st.consume_edit_request() is None


def test_edit_key_ignored_without_a_file():
    st = ExplorerState()
    st.update_jobs([_view("a", "PASS", id="aaaaaaaa1")])
    st.jobs[0]["file_path"] = ""  # a row with no editable file
    assert st.handle_key("e") is False
    assert st.consume_edit_request() is None


def test_cancel_requested_while_running_does_not_quit():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.running = True
    # q/escape while a run is in flight requests cancellation, not quit.
    assert st.handle_key("q") is True
    assert st.quit is False
    assert st.cancel_requested is True
    assert st.consume_cancel_request() is True
    # Edge-triggered: consumed once.
    assert st.consume_cancel_request() is False


def test_escape_also_requests_cancel_while_running():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.running = True
    assert st.handle_key("escape") is True
    assert st.quit is False
    assert st.consume_cancel_request() is True


def test_quit_when_not_running():
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.running is False
    assert st.handle_key("q") is True
    assert st.quit is True
    assert st.cancel_requested is False
    assert st.consume_cancel_request() is False


def test_handle_key_unknown_returns_false():
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.handle_key("z") is False


def test_run_prompt_opens_types_and_submits():
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.handle_key(":") is True
    assert st.mode == "prompt"
    for ch in "examples":
        assert st.handle_key(ch) is True
    assert st.prompt_buffer == "examples"
    assert st.handle_key("backspace") is True
    assert st.prompt_buffer == "example"
    assert st.handle_key("enter") is True
    # Submitting leaves prompt mode and records the (edge-triggered) request.
    assert st.mode == "list"
    assert st.consume_run_input_request() == "example"
    assert st.consume_run_input_request() is None


def test_run_prompt_escape_cancels_without_request():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.handle_key(":")
    for ch in "foo":
        st.handle_key(ch)
    assert st.handle_key("escape") is True
    assert st.mode == "list"
    assert st.consume_run_input_request() is None


def test_run_prompt_empty_submit_is_noop():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.handle_key(":")
    st.handle_key("enter")  # nothing typed
    assert st.mode == "list"
    assert st.consume_run_input_request() is None


def test_run_prompt_ignores_control_key_names():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.handle_key(":")
    # Logical multi-char key names (arrows, page keys) are not input characters.
    assert st.handle_key("down") is False
    assert st.handle_key("pagedown") is False
    assert st.prompt_buffer == ""


def test_run_prompt_refused_while_running():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.running = True
    assert st.handle_key(":") is False
    assert st.mode == "list"


def test_empty_state_is_safe():
    st = ExplorerState()
    assert st.selected is None
    assert st.selected_id is None
    st.move(1)
    st.move_end()
    assert st.cursor == 0
    # renders without raising
    render_table(st)


def test_render_frame_contains_job_names_and_summary():
    st = ExplorerState()
    st.update_jobs(_rows())
    summary = {
        "root": "/ws/.canary",
        "session_count": 1,
        "latest_session": "S1",
        "spec_count": 3,
        "tags": [],
        "version": "0.0.0",
    }
    frame = render_frame(st, summary, {"PASS": 2, "FAIL": 1})
    console = Console(width=100, file=None, record=True)
    console.print(frame)
    out = console.export_text()
    assert "a" in out and "b" in out and "c" in out
    assert "PASS=2" in out
    assert "FAIL=1" in out
    assert "/ws/.canary" in out


def test_render_frame_shows_detail_when_open():
    st = ExplorerState()
    st.update_jobs(_rows())
    st.set_filter("FAIL")
    st.toggle_detail()
    summary = {
        "root": "/ws",
        "session_count": 1,
        "latest_session": "",
        "spec_count": 3,
        "tags": [],
        "version": "0.0.0",
    }
    console = Console(width=100, record=True)
    console.print(render_frame(st, summary, {"FAIL": 1}))
    out = console.export_text()
    assert "detail" in out
    assert "boom" in out  # the FAIL row's reason


def _rendered_line_count(console, renderable):
    options = console.options.update(height=None)
    return len(console.render_lines(renderable, options, pad=False))


def test_render_frame_shows_run_progress_when_active():
    """While a run is active, the frame includes the live progress panel."""
    from _canary.tui.progress import RunProgress

    st = ExplorerState()
    st.update_jobs([_view("basic.x=1", "PASS", id="000000001")])
    summary = _summary()

    p = RunProgress()
    p.begin(total=2)
    from _canary.events import Event

    p.on_event(Event("job_started", {"job": {"id": "a", "qsize": 2, "status": ""}}))
    p.on_event(Event("job_finished", {"job": {"id": "a", "qsize": 2, "status": "PASS"}}))

    console = Console(width=80, height=40)
    with console.capture() as cap:
        console.print(render_frame(st, summary, {"PASS": 1}, p.snapshot()))
    out = cap.get()
    assert "running" in out
    assert "1/2" in out  # finished/total

    # When no run is active, the panel is absent.
    p.end()
    with console.capture() as cap:
        console.print(render_frame(st, summary, {"PASS": 1}, p.snapshot()))
    assert "running:" not in cap.get()


def test_footer_hint_switches_to_cancel_while_running():
    """The footer advertises q/esc as cancel (not quit) while a run is active."""
    from _canary.tui.render import render_footer

    st = ExplorerState()
    st.update_jobs(_rows())
    console = Console(width=100, record=True)
    console.print(render_footer(st))
    assert "cancel run" not in console.export_text()

    st.running = True
    console = Console(width=100, record=True)
    console.print(render_footer(st))
    assert "cancel run" in console.export_text()


def test_frame_fits_terminal_height_when_sized():
    """With the body sized by the runner, the frame must not exceed the terminal.

    Regression guard: a fixed chrome estimate under-counted the wrapping
    header/footer, so more jobs than fit rendered past the bottom of a short
    terminal instead of scrolling.
    """
    from _canary.tui.app import _body_height

    st = ExplorerState()
    st.update_jobs([_view(f"j{i:02d}", "PASS", id=f"{i:09d}") for i in range(40)])
    summary = _summary(root="/a/deliberately/long/workspace/path/that/wraps/.canary")
    counts = {"PASS": 40}

    for height in (12, 20, 40):
        console = Console(width=80, height=height)
        st.set_viewport_height(_body_height(console, st, summary, counts))
        st.move_end()  # worst case: cursor forces a scroll to the last window
        rendered = _rendered_line_count(console, render_frame(st, summary, counts))
        assert rendered <= height, f"frame overflowed at LINES={height}: {rendered} lines"
        # And the selected (last) row is within the visible window.
        assert 0 <= st.window_cursor < max(1, st.viewport_height)
