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


def test_handle_key_unknown_returns_false():
    st = ExplorerState()
    st.update_jobs(_rows())
    assert st.handle_key("z") is False


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
