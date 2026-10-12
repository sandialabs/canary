# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for _canary.history: conservative per-job runtime estimates."""

import json
from pathlib import Path
from typing import Any
from typing import Generator

import pytest

import _canary.history as his


class HistoryStore(his.HistoryStore):
    def record(self, job: Any) -> None:
        """store relevant information for this run"""
        assert self.root is not None
        file = self.path_for(job)
        assert file is not None
        file.parent.mkdir(parents=True, exist_ok=True)
        cache = {".version": [3, 0], "meta": {}}
        metrics = cache.setdefault("metrics", {})
        t = metrics.setdefault("time", {})
        t["mean"] = job.history["mean"]
        t["min"] = job.history["min"]
        t["max"] = job.history["max"]
        t["variance"] = job.history["variance"]
        t["count"] = job.history["count"]
        with open(file, "w") as fh:
            json.dump({"cache": cache}, fh)


class FakeJob:
    def __init__(
        self,
        *,
        timeout: float = 300.0,
        multiplier: float = 1.0,
        history: dict[str, Any] | None = None,
        broken_cache: bool = False,
    ) -> None:
        self.id = "f" * 64
        self._timeout = timeout
        self.multiplier = multiplier
        self.history = history or {"mean": 1.0, "max": 1.0, "min": 1.0, "variance": 0, "count": 1}
        self.broken_cache = broken_cache

    @property
    def timeout(self):
        return self._timeout


def history(
    mean: float,
    maximum: float | None = None,
    minimum: float | None = None,
    variance: float | None = None,
    count: int = 2,
) -> dict[str, float]:
    return {
        "mean": mean,
        "max": mean if maximum is None else maximum,
        "min": mean if minimum is None else minimum,
        "variance": 0.05 * mean if variance is None else variance,
        "count": count,
    }


@pytest.fixture
def cold_store() -> HistoryStore:
    return HistoryStore(None)


@pytest.fixture
def tmp_store(tmp_path: Path) -> Generator[HistoryStore]:
    store = HistoryStore(tmp_path)
    yield store


def test_cold_job_uses_default_fraction_of_timeout(cold_store: HistoryStore):
    job = FakeJob(timeout=300.0)
    assert his.COLD_RUNTIME_FRACTION == 0.75
    assert his.estimate_runtime(job, store=cold_store) == 225.0


def test_history_no_variance_is_mean(tmp_store: HistoryStore):
    job = FakeJob(timeout=300.0, history=history(60.0, variance=0))
    tmp_store.record(job)
    assert his.estimate_runtime(job, store=tmp_store) == 60.0


def test_history_variance_is_expected(tmp_store: HistoryStore):
    job = FakeJob(timeout=300.0, history=history(53.75, variance=218.6875))
    tmp_store.record(job)
    t = his.estimate_runtime(job, store=tmp_store)
    assert 61.144 == pytest.approx(t)
