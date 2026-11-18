# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""ViewManager takes its inputs and never calls back into the workspace."""

from types import SimpleNamespace
from typing import Any

from _canary.view import ResultsView
from _canary.view import ViewManager
from _canary.view import ViewSettings


def _manager(tmp_path, when: str, **kwargs: Any) -> ViewManager:
    settings = ViewSettings(when=when)  # type: ignore[arg-type]
    return ViewManager(root=tmp_path, cache_dir=tmp_path / "cache", settings=settings, **kwargs)


def test_live_view_is_returned_by_start_for_the_caller_to_register(tmp_path):
    manager = _manager(tmp_path, "always")
    view = manager.start()
    assert isinstance(view, ResultsView)
    assert view.dir.exists()
    assert manager.start() is None  # idempotent


def test_disabled_and_deferred_views_are_not_returned_by_start(tmp_path):
    assert _manager(tmp_path, "never").start() is None
    assert _manager(tmp_path, "on_success").start() is None


def test_deferred_finish_falls_back_to_session_jobs_then_load_jobs(tmp_path):
    passing = SimpleNamespace(status=SimpleNamespace(is_failure=lambda: False))
    calls: list[int] = []

    def load_jobs() -> list[Any]:
        calls.append(1)
        return [passing]

    with_jobs = _manager(tmp_path, "on_failure", jobs=[passing], load_jobs=load_jobs)
    with_jobs.start()
    assert with_jobs.finish() is None  # nothing failed: no view
    assert calls == []

    without_jobs = _manager(tmp_path, "on_failure", load_jobs=load_jobs)
    without_jobs.start()
    assert without_jobs.finish() is None
    assert calls == [1]
