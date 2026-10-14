# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for _canary.history: conservative per-job runtime estimates."""

import time
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
        meta = {
            "what": "meta",
            "version": his.store.SCHEMA,
            "id": job.id,
            "name": job.id,
            "root": "/tmp",
            "path": "path.pyt",
            "parameters": {},
            "totals": {},
        }
        run: dict[str, Any] = {
            "what": "record",
            "version": his.store.SCHEMA,
            "recorded_at": round(time.time(), 3),
            "status": "success",
            "duration": round(job.duration, 3),
            "timeout": float(job.timeout),
            "timeiout_multiplier": 1.0,
            "file_hash": "abcdefg",
            "host": "myhost",
        }
        if not file.exists():
            self._append(file, meta, run)
        else:
            self._append(file, run)


class FakeJob:
    def __init__(
        self,
        *,
        timeout: float = 300.0,
        multiplier: float = 1.0,
        duration: float = 1.0,
        broken_cache: bool = False,
    ) -> None:
        self.id = "f" * 64
        self._timeout = timeout
        self.multiplier = multiplier
        self.duration = duration
        self.broken_cache = broken_cache

    @property
    def timeout(self):
        return self._timeout


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
    job = FakeJob(timeout=300.0, duration=60.0)
    tmp_store.record(job)
    t = his.estimate_runtime(job, store=tmp_store)
    assert (60.0 + 0.1 * 0.5 * 60.0) == pytest.approx(t)


def test_history_variance_is_expected(tmp_store: HistoryStore):
    job = FakeJob(timeout=300.0, duration=40)
    tmp_store.record(job)
    job = FakeJob(timeout=300.0, duration=45)
    tmp_store.record(job)
    job = FakeJob(timeout=300.0, duration=80)
    tmp_store.record(job)
    job = FakeJob(timeout=300.0, duration=50)
    tmp_store.record(job)
    t = his.estimate_runtime(job, store=tmp_store)
    assert 62.735 == pytest.approx(t)
