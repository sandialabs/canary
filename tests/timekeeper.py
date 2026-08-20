# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import pytest

from _canary.timekeeper import Timekeeper


def test_timekeeper_initial_state() -> None:
    tk = Timekeeper()

    assert tk._submitted == -1.0
    assert tk._staged == -1.0
    assert tk._started == -1.0
    assert tk._stopped == -1.0
    assert tk._finished == -1.0

    assert tk.pending() == -1.0
    assert tk.staging() == -1.0
    assert tk.running() == -1.0
    assert tk.finishing() == -1.0
    assert tk.total() == -1.0
    assert tk.elapsed() == -1.0


def test_open_sets_submitted() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)

    assert tk._submitted == 10.0
    assert tk._staged == -1.0
    assert tk._started == -1.0
    assert tk._stopped == -1.0
    assert tk._finished == -1.0


def test_stage_sets_staged_and_defaults_submitted() -> None:
    tk = Timekeeper()

    tk.stage(at=20.0)

    assert tk._submitted == 20.0
    assert tk._staged == 20.0
    assert tk._started == -1.0
    assert tk._stopped == -1.0
    assert tk._finished == -1.0


def test_stage_preserves_existing_submitted() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)

    assert tk._submitted == 10.0
    assert tk._staged == 20.0


def test_start_sets_started_and_defaults_previous_times() -> None:
    tk = Timekeeper()

    tk.start(at=30.0)

    assert tk._submitted == 30.0
    assert tk._staged == 30.0
    assert tk._started == 30.0
    assert tk._stopped == -1.0
    assert tk._finished == -1.0


def test_start_preserves_existing_previous_times() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)

    assert tk._submitted == 10.0
    assert tk._staged == 20.0
    assert tk._started == 30.0


def test_stop_sets_stopped_and_defaults_previous_times() -> None:
    tk = Timekeeper()

    tk.stop(at=40.0)

    assert tk._submitted == 40.0
    assert tk._staged == 40.0
    assert tk._started == 40.0
    assert tk._stopped == 40.0
    assert tk._finished == -1.0


def test_stop_preserves_existing_previous_times() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)

    assert tk._submitted == 10.0
    assert tk._staged == 20.0
    assert tk._started == 30.0
    assert tk._stopped == 40.0
    assert tk._finished == -1.0


def test_close_sets_finished_and_defaults_previous_times() -> None:
    tk = Timekeeper()

    tk.close(at=50.0)

    assert tk._submitted == 50.0
    assert tk._staged == 50.0
    assert tk._started == 50.0
    assert tk._stopped == 50.0
    assert tk._finished == 50.0


def test_close_preserves_existing_previous_times() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)
    tk.close(at=50.0)

    assert tk._submitted == 10.0
    assert tk._staged == 20.0
    assert tk._started == 30.0
    assert tk._stopped == 40.0
    assert tk._finished == 50.0


def test_maybe_open_only_sets_missing_value() -> None:
    tk = Timekeeper()

    tk.maybe_open(at=10.0)
    tk.maybe_open(at=20.0)

    assert tk._submitted == 10.0


def test_maybe_stage_only_sets_missing_value() -> None:
    tk = Timekeeper()

    tk.stage(at=10.0)
    tk.maybe_stage(at=20.0)

    assert tk._staged == 10.0


def test_maybe_start_only_sets_missing_value() -> None:
    tk = Timekeeper()

    tk.start(at=10.0)
    tk.maybe_start(at=20.0)

    assert tk._started == 10.0


def test_maybe_stop_only_sets_missing_value() -> None:
    tk = Timekeeper()

    tk.stop(at=10.0)
    tk.maybe_stop(at=20.0)

    assert tk._stopped == 10.0


def test_maybe_close_only_sets_missing_value() -> None:
    tk = Timekeeper()

    tk.close(at=10.0)
    tk.maybe_close(at=20.0)

    assert tk._finished == 10.0


def test_phase_durations() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=45.0)
    tk.close(at=50.0)

    assert tk.pending() == 10.0
    assert tk.staging() == 10.0
    assert tk.running() == 15.0
    assert tk.finishing() == 5.0
    assert tk.total() == 40.0
    assert tk.elapsed() == 40.0


def test_phase_durations_return_negative_one_until_required_endpoints_exist() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)

    assert tk.pending() == -1.0
    assert tk.staging() == -1.0
    assert tk.running() == -1.0
    assert tk.finishing() == -1.0
    assert tk.total() == -1.0


def test_live_pending_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)

    monkeypatch.setattr("time.time", lambda: 14.0)

    assert tk.pending(live=False) == -1.0
    assert tk.pending(live=True) == 4.0


def test_live_staging_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)
    tk.stage(at=20.0)

    monkeypatch.setattr("time.time", lambda: 27.0)

    assert tk.staging(live=False) == -1.0
    assert tk.staging(live=True) == 7.0


def test_live_running_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)

    monkeypatch.setattr("time.time", lambda: 45.0)

    assert tk.running(live=False) == -1.0
    assert tk.running(live=True) == 15.0


def test_live_finishing_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=45.0)

    monkeypatch.setattr("time.time", lambda: 50.0)

    assert tk.finishing(live=False) == -1.0
    assert tk.finishing(live=True) == 5.0


def test_live_total_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    tk = Timekeeper()
    tk.open(at=10.0)

    monkeypatch.setattr("time.time", lambda: 55.0)

    assert tk.total(live=False) == -1.0
    assert tk.total(live=True) == 45.0
    assert tk.elapsed(live=True) == 45.0


def test_reset_restores_initial_state() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)
    tk.close(at=50.0)

    tk.reset()

    assert tk._submitted == -1.0
    assert tk._staged == -1.0
    assert tk._started == -1.0
    assert tk._stopped == -1.0
    assert tk._finished == -1.0


def test_sync_copies_state() -> None:
    source = Timekeeper()
    target = Timekeeper()

    source.open(at=10.0)
    source.stage(at=20.0)
    source.start(at=30.0)
    source.stop(at=40.0)
    source.close(at=50.0)

    target.sync(source)

    assert target._submitted == 10.0
    assert target._staged == 20.0
    assert target._started == 30.0
    assert target._stopped == 40.0
    assert target._finished == 50.0


def test_serialize_roundtrip() -> None:
    tk = Timekeeper()

    tk.open(at=10.0)
    tk.stage(at=20.0)
    tk.start(at=30.0)
    tk.stop(at=40.0)
    tk.close(at=50.0)

    data = tk.__serialize__()
    other = Timekeeper.__deserialize__(dict(data))

    assert other._submitted == 10.0
    assert other._staged == 20.0
    assert other._started == 30.0
    assert other._stopped == 40.0
    assert other._finished == 50.0


def test_deserialize_current_schema() -> None:
    tk = Timekeeper.__deserialize__(
        {"_submitted": 10.0, "_staged": 20.0, "_started": 30.0, "_stopped": 40.0, "_finished": 50.0}
    )

    assert tk._submitted == 10.0
    assert tk._staged == 20.0
    assert tk._started == 30.0
    assert tk._stopped == 40.0
    assert tk._finished == 50.0


def test_deserialize_private_field_schema() -> None:
    tk = Timekeeper.__deserialize__(
        {"_submitted": 10.0, "_staged": 20.0, "_started": 30.0, "_stopped": 40.0, "_finished": 50.0}
    )

    assert tk._submitted == 10.0
    assert tk._staged == 20.0
    assert tk._started == 30.0
    assert tk._stopped == 40.0
    assert tk._finished == 50.0


def test_delta_does_not_clamp_negative_intervals() -> None:
    tk = Timekeeper()

    tk.open(at=20.0)
    tk.stage(at=10.0)

    assert tk.pending() == -10.0
