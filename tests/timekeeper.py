# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.timekeeper import Timekeeper


def test_timekeeper_initial_state() -> None:
    tk = Timekeeper()

    assert tk.opened == -1.0
    assert tk.launched == -1.0
    assert tk.started == -1.0
    assert tk.finished == -1.0
    assert tk.closed == -1.0

    assert tk.submitted == -1.0
    assert tk.returned == -1.0

    assert tk.queued() == -1.0
    assert tk.startup() == -1.0
    assert tk.running() == -1.0
    assert tk.duration() == -1.0
    assert tk.teardown() == -1.0
    assert tk.total() == -1.0


def test_open_sets_opened() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)

    assert tk.opened == 10.0
    assert tk.submitted == 10.0
    assert tk.launched == -1.0
    assert tk.started == -1.0
    assert tk.finished == -1.0
    assert tk.closed == -1.0


def test_launch_sets_launched_and_defaults_opened() -> None:
    tk = Timekeeper()

    tk.launch(at=20.0)

    assert tk.opened == 20.0
    assert tk.launched == 20.0
    assert tk.started == -1.0
    assert tk.finished == -1.0
    assert tk.closed == -1.0


def test_launch_preserves_existing_opened() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=20.0)

    assert tk.opened == 10.0
    assert tk.launched == 20.0


def test_start_sets_started_and_defaults_opened_and_launched() -> None:
    tk = Timekeeper()

    tk.start(at=30.0)

    assert tk.opened == 30.0
    assert tk.launched == 30.0
    assert tk.started == 30.0
    assert tk.finished == -1.0
    assert tk.closed == -1.0


def test_start_preserves_existing_opened_and_launched() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)

    assert tk.opened == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0


def test_stop_sets_finished_and_defaults_missing_previous_times() -> None:
    tk = Timekeeper()

    tk.stop(at=40.0)

    assert tk.opened == 40.0
    assert tk.launched == 40.0
    assert tk.started == 40.0
    assert tk.finished == 40.0
    assert tk.closed == -1.0


def test_stop_preserves_existing_previous_times() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)

    assert tk.opened == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == -1.0


def test_close_sets_closed_and_defaults_missing_previous_times() -> None:
    tk = Timekeeper()

    tk.close(at=50.0)

    assert tk.opened == 50.0
    assert tk.launched == 50.0
    assert tk.started == 50.0
    assert tk.finished == 50.0
    assert tk.closed == 50.0


def test_close_preserves_existing_previous_times() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)
    tk.close(at=50.0)

    assert tk.opened == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 50.0


def test_submitted_alias_reads_and_writes_opened() -> None:
    tk = Timekeeper()

    tk.submitted = 12.5

    assert tk.opened == 12.5
    assert tk.submitted == 12.5


def test_returned_alias_reads_and_writes_closed() -> None:
    tk = Timekeeper()

    tk.returned = 99.5

    assert tk.closed == 99.5
    assert tk.returned == 99.5


def test_phase_durations() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=12.0)
    tk.start(at=15.0)
    tk.stop(at=25.0)
    tk.close(at=28.0)

    assert tk.queued() == 2.0
    assert tk.startup() == 3.0
    assert tk.running() == 10.0
    assert tk.duration() == 10.0
    assert tk.teardown() == 3.0
    assert tk.total() == 18.0


def test_phase_durations_return_negative_one_until_start_exists() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)

    assert tk.queued() == -1.0
    assert tk.startup() == -1.0
    assert tk.running() == -1.0
    assert tk.teardown() == -1.0
    assert tk.total() == -1.0


def test_live_queued_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.opened = 10.0

    monkeypatch.setattr("time.time", lambda: 14.0)

    assert tk.queued(live=False) == -1.0
    assert tk.queued(live=True) == 4.0


def test_live_startup_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)
    tk.launch(at=20.0)

    monkeypatch.setattr("time.time", lambda: 27.0)

    assert tk.startup(live=False) == -1.0
    assert tk.startup(live=True) == 7.0


def test_live_running_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)

    monkeypatch.setattr("time.time", lambda: 45.0)

    assert tk.running(live=False) == -1.0
    assert tk.running(live=True) == 15.0
    assert tk.duration(live=True) == 15.0


def test_live_teardown_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)

    monkeypatch.setattr("time.time", lambda: 46.0)

    assert tk.teardown(live=False) == -1.0
    assert tk.teardown(live=True) == 6.0


def test_live_total_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)

    monkeypatch.setattr("time.time", lambda: 70.0)

    assert tk.total(live=False) == -1.0
    assert tk.total(live=True) == 60.0


def test_reset_restores_initial_state() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)
    tk.close(at=50.0)

    tk.reset()

    assert tk.opened == -1.0
    assert tk.launched == -1.0
    assert tk.started == -1.0
    assert tk.finished == -1.0
    assert tk.closed == -1.0


def test_update_sets_all_fields() -> None:
    tk = Timekeeper()

    tk.update(opened=10.0, launched=20.0, started=30.0, finished=40.0, closed=50.0)

    assert tk.opened == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 50.0


def test_update_accepts_submitted_alias_for_opened() -> None:
    tk = Timekeeper()

    tk.update(submitted=10.0, launched=20.0, started=30.0, finished=40.0, closed=50.0)

    assert tk.opened == 10.0
    assert tk.submitted == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 50.0


def test_update_opened_takes_precedence_over_submitted_alias() -> None:
    tk = Timekeeper()

    tk.update(opened=11.0, submitted=10.0)

    assert tk.opened == 11.0
    assert tk.submitted == 11.0


def test_update_fills_launched_from_started() -> None:
    tk = Timekeeper()

    tk.update(opened=10.0, started=30.0)

    assert tk.opened == 10.0
    assert tk.launched == 30.0
    assert tk.started == 30.0


def test_update_fills_closed_from_finished() -> None:
    tk = Timekeeper()

    tk.update(opened=10.0, launched=20.0, started=30.0, finished=40.0)

    assert tk.closed == 40.0


def test_update_fills_opened_from_launched_when_missing() -> None:
    tk = Timekeeper()

    tk.update(launched=20.0)

    assert tk.opened == 20.0


def test_update_fills_opened_from_started_when_opened_and_launched_missing() -> None:
    tk = Timekeeper()

    tk.update(started=30.0)

    assert tk.opened == 30.0
    assert tk.launched == 30.0


def test_serialize_new_schema() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.launch(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)
    tk.close(at=50.0)

    assert tk.__serialize__() == {
        "opened": 10.0,
        "launched": 20.0,
        "started": 30.0,
        "finished": 40.0,
        "closed": 50.0,
    }


def test_deserialize_new_schema() -> None:
    tk = Timekeeper.__deserialize__(
        {
            "opened": 10.0,
            "launched": 20.0,
            "started": 30.0,
            "finished": 40.0,
            "closed": 50.0,
        }
    )

    assert tk.opened == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 50.0


def test_deserialize_old_schema_maps_submitted_to_opened_and_defaults_launched_closed() -> None:
    tk = Timekeeper.__deserialize__(
        {
            "submitted": 10.0,
            "started": 30.0,
            "finished": 40.0,
        }
    )

    assert tk.opened == 10.0
    assert tk.submitted == 10.0
    assert tk.launched == 30.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 40.0
    assert tk.returned == 40.0


def test_deserialize_mixed_schema_prefers_new_fields() -> None:
    tk = Timekeeper.__deserialize__(
        {
            "submitted": 1.0,
            "opened": 10.0,
            "launched": 20.0,
            "started": 30.0,
            "finished": 40.0,
            "closed": 50.0,
        }
    )

    assert tk.opened == 10.0
    assert tk.launched == 20.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 50.0


def test_deserialize_ignores_old_mark_field() -> None:
    tk = Timekeeper.__deserialize__(
        {
            "submitted": 10.0,
            "started": 30.0,
            "finished": 40.0,
            "mark": 999.0,
        }
    )

    assert not hasattr(tk, "mark")
    assert tk.opened == 10.0
    assert tk.launched == 30.0
    assert tk.started == 30.0
    assert tk.finished == 40.0
    assert tk.closed == 40.0


def test_delta_does_not_clamp_negative_intervals() -> None:
    tk = Timekeeper()

    tk.open(at=20.0)
    tk.launch(at=10.0)

    assert tk.queued() == -10.0
