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


def test_hpc_batch_queued_time_preserved_after_completion() -> None:
    """Regression test: queued time must not collapse to 0 after a batch completes.

    HPC batch lifecycle:
      T0 = submitted (on_submit)
      T1 = job starts on nodes (on_stage + on_start, both at the same time)
      T2 = job stops
      T3 = job finished

    Before the fix, on_start() was called without on_stage(), so start()
    backfilled _staged = _submitted (= T0), making pending() = T0 - T0 = 0.

    After the fix, on_stage(at=T1) is called first, so _staged = T1 and
    pending() = T1 - T0 = the real queue-wait duration.
    """
    T0, T1, T2, T3 = 1000.0, 1060.0, 1120.0, 1121.0  # 60 s queue wait, 60 s running
    tk = Timekeeper()

    # Simulate the corrected HPC batch lifecycle
    tk.open(at=T0)       # on_submit
    tk.stage(at=T1)      # on_stage  (job leaves scheduler queue)
    tk.start(at=T1)      # on_start  (same timestamp — HPC has no separate staging phase)
    tk.stop(at=T2)       # on_stop
    tk.close(at=T3)      # on_finish

    assert tk.pending() == pytest.approx(60.0), "queued time should be T1 - T0 = 60 s"
    assert tk.running() == pytest.approx(60.0), "running time should be T2 - T1 = 60 s"
    assert tk.staging() == pytest.approx(0.0), "staging duration is 0 (stage and start at same T)"
    assert tk.total() == pytest.approx(T3 - T0)


def test_hpc_batch_queued_time_live_before_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """While the job is queued (staged not yet set), live pending increments."""
    T0 = 1000.0
    tk = Timekeeper()
    tk.open(at=T0)  # submitted; _staged is still -1.0

    monkeypatch.setattr("_canary.timekeeper.time", __import__("time"))
    monkeypatch.setattr("time.time", lambda: T0 + 45.0)

    assert tk.pending(live=True) == pytest.approx(45.0), "live pending should grow while queued"
    assert tk._staged == -1.0, "_staged must remain unset until on_stage() fires"


def test_start_without_prior_stage_backfills_staged_to_submitted() -> None:
    """start() without a prior stage() backfills _staged = _submitted (existing behaviour).

    This is the old HPC path and explains why calling on_start() alone collapsed
    the queued time.  The test documents the behaviour so future refactors don't
    silently break the backfill contract for non-HPC jobs.
    """
    tk = Timekeeper()
    tk.open(at=100.0)
    tk.start(at=200.0)

    assert tk._staged == 100.0, "start() backfills _staged to _submitted when _staged is unset"
    assert tk.pending() == pytest.approx(0.0), "pending collapses to 0 — the bug in the old HPC path"
    assert tk.running(live=True) >= 0.0
