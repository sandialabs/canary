# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Tests for _canary.history: conservative per-job runtime estimates."""

from __future__ import annotations

import json as pyjson
import time
from pathlib import Path
from typing import Any

import pytest

import _canary.history as his
import _canary.history.store as store_mod

JOB_ID = "f" * 64


class SyntheticHistoryStore(his.HistoryStore):
    """HistoryStore variant that records simple synthetic jobs.

    This keeps the runtime-estimation tests focused on history behavior without
    needing a full JobSpec/Status/Timekeeper object graph.
    """

    def record(self, job: Any) -> None:
        if self.root is None or not self.mode.allow_write:
            return

        file = self.path_for(job)
        assert file is not None
        file.parent.mkdir(parents=True, exist_ok=True)

        meta = {
            "what": "meta",
            "version": store_mod.SCHEMA,
            "id": job.id,
            "name": job.id,
            "root": "/tmp",
            "path": "path.pyt",
            "parameters": {},
            "totals": {},
        }
        run: dict[str, Any] = {
            "what": "record",
            "version": store_mod.SCHEMA,
            "recorded_at": round(time.time(), 3),
            "status": getattr(job, "status", "success"),
            "duration": round(job.duration, 3) if job.duration is not None else None,
            "timeout": float(job.timeout),
            "timeout_multiplier": 1.0,
            "file_hash": "abcdefg",
            "host": "myhost",
        }
        if not file.exists():
            self._append(file, meta, run)
        else:
            self._append(file, run)


class RecordingStore(his.HistoryStore):
    """HistoryStore variant used to test public record() write gating."""

    def _record(self, job: Any) -> None:
        file = self.path_for(job)
        assert file is not None
        file.parent.mkdir(parents=True, exist_ok=True)

        meta = {
            "what": "meta",
            "version": store_mod.SCHEMA,
            "id": job.id,
            "name": job.id,
            "root": "/tmp",
            "path": "path.pyt",
            "parameters": {},
            "totals": {},
        }
        run = {
            "what": "record",
            "version": store_mod.SCHEMA,
            "recorded_at": round(time.time(), 3),
            "status": "success",
            "duration": round(job.duration, 3),
            "timeout": float(job.timeout),
            "timeout_multiplier": 1.0,
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
        duration: float | None = 1.0,
        status: str = "success",
        job_id: str = JOB_ID,
    ) -> None:
        self.id = job_id
        self._timeout = timeout
        self.multiplier = multiplier
        self.duration = duration
        self.status = status

    @property
    def timeout(self) -> float:
        return self._timeout


class FakeSpec:
    id = JOB_ID
    file_root = Path("/tmp")
    file_path = Path("path.pyt")
    parameters: dict[str, Any] = {}

    def display_name(self) -> str:
        return self.id


class FullFakeJob(FakeJob):
    """Minimal job shape sufficient for _compact(), which calls _meta(job)."""

    spec = FakeSpec()


class FakeParser:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def add_argument(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


@pytest.fixture(autouse=True)
def clean_history_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep history-mode tests independent from the developer environment."""

    monkeypatch.delenv("CANARY_HISTORY_MODE", raising=False)
    monkeypatch.delenv("CANARY_DISABLE_HISTORY", raising=False)
    monkeypatch.delenv("CANARY_CACHE_DIR", raising=False)
    monkeypatch.setattr(store_mod.config, "getoption", lambda *args, **kwargs: None)
    monkeypatch.setattr(store_mod.config, "get", lambda *args, **kwargs: None)
    store_mod._cache_dir_logged = False


@pytest.fixture
def cold_store() -> SyntheticHistoryStore:
    return SyntheticHistoryStore(None)


@pytest.fixture
def tmp_store(tmp_path: Path) -> SyntheticHistoryStore:
    return SyntheticHistoryStore(tmp_path)


def history_path(root: Path, job: FakeJob) -> Path:
    return root / "jobs" / job.id[:2] / f"{job.id[2:]}.jsonl"


def seed_history(
    root: Path, job: FakeJob, durations: list[float | None], *, statuses: list[str] | None = None
) -> Path:
    statuses = statuses or ["success"] * len(durations)
    assert len(statuses) == len(durations)

    file = history_path(root, job)
    file.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = [
        {
            "what": "meta",
            "version": store_mod.SCHEMA,
            "id": job.id,
            "name": job.id,
            "root": "/tmp",
            "path": "path.pyt",
            "parameters": {},
            "totals": {},
        }
    ]
    records.extend(
        {
            "what": "record",
            "version": store_mod.SCHEMA,
            "recorded_at": 1000.0 + i,
            "status": status,
            "duration": duration,
            "timeout": float(job.timeout),
            "timeout_multiplier": 1.0,
            "file_hash": "abcdefg",
            "host": "myhost",
        }
        for i, (duration, status) in enumerate(zip(durations, statuses))
    )

    file.write_text("".join(pyjson.dumps(record) + "\n" for record in records))
    return file


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [pyjson.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_cold_job_uses_default_fraction_of_timeout(cold_store: SyntheticHistoryStore) -> None:
    job = FakeJob(timeout=300.0)
    assert his.COLD_RUNTIME_FRACTION == 0.75
    assert his.estimate_runtime(job, store=cold_store) == 225.0


def test_history_no_variance_is_mean(tmp_store: SyntheticHistoryStore) -> None:
    job = FakeJob(timeout=300.0, duration=60.0)
    tmp_store.record(job)

    t = his.estimate_runtime(job, store=tmp_store)

    assert (60.0 + 0.1 * 0.5 * 60.0) == pytest.approx(t)


def test_history_variance_is_expected(tmp_store: SyntheticHistoryStore) -> None:
    for duration in (40.0, 45.0, 80.0, 50.0):
        tmp_store.record(FakeJob(timeout=300.0, duration=duration))

    t = his.estimate_runtime(FakeJob(timeout=300.0), store=tmp_store)

    assert 62.735 == pytest.approx(t)


def test_runtime_statistics_from_durations_rejects_empty() -> None:
    with pytest.raises(ValueError, match="No durations"):
        store_mod.RuntimeStatistics.from_durations([])


def test_runtime_statistics_from_single_duration() -> None:
    stats = store_mod.RuntimeStatistics.from_durations([12.5])

    assert stats.count == 1
    assert stats.mean == 12.5
    assert stats.variance == 0.0
    assert stats.std == 0.0
    assert stats.min == 12.5
    assert stats.max == 12.5


def test_durations_filters_to_successful_records_with_duration() -> None:
    records = [
        {"status": "success", "duration": 1.0},
        {"status": "failed", "duration": 2.0},
        {"status": "success", "duration": None},
        {"status": "success", "duration": 3.5},
        {"status": "skipped", "duration": 4.0},
    ]

    assert store_mod._durations(records) == [1.0, 3.5]
    assert store_mod._durations(records, status="failed") == [2.0]


@pytest.mark.parametrize(
    ("mode", "read_enabled", "write_enabled"),
    [
        (store_mod.HistoryMode.NONE, False, False),
        (store_mod.HistoryMode.READ, True, False),
        (store_mod.HistoryMode.WRITE, False, True),
        (store_mod.HistoryMode.READWRITE, True, True),
    ],
)
def test_history_mode_read_write_flags(
    mode: store_mod.HistoryMode, read_enabled: bool, write_enabled: bool
) -> None:
    assert mode.allow_read is read_enabled
    assert mode.allow_write is write_enabled


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("none", store_mod.HistoryMode.NONE),
        ("r", store_mod.HistoryMode.READ),
        ("w", store_mod.HistoryMode.WRITE),
        ("rw", store_mod.HistoryMode.READWRITE),
    ],
)
def test_history_mode_get_from_environment(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: store_mod.HistoryMode
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", raw)

    assert store_mod.HistoryMode.get() is expected


def test_history_mode_cli_option_precedes_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "none")
    monkeypatch.setattr(
        store_mod.config,
        "getoption",
        lambda name, *args, **kwargs: "r" if name == "history_mode" else None,
    )

    assert store_mod.HistoryMode.get() is store_mod.HistoryMode.READ


def test_history_mode_invalid_environment_warns_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "bogus")

    assert store_mod.HistoryMode.get() is store_mod.HistoryMode.READWRITE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", store_mod.HistoryMode.NONE),
        ("true", store_mod.HistoryMode.NONE),
        ("TRUE", store_mod.HistoryMode.NONE),
        ("yes", store_mod.HistoryMode.NONE),
        ("on", store_mod.HistoryMode.NONE),
        ("0", store_mod.HistoryMode.READWRITE),
        ("false", store_mod.HistoryMode.READWRITE),
        ("no", store_mod.HistoryMode.READWRITE),
        ("off", store_mod.HistoryMode.READWRITE),
    ],
)
def test_legacy_disable_history_environment(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: store_mod.HistoryMode
) -> None:
    monkeypatch.setenv("CANARY_DISABLE_HISTORY", raw)

    assert store_mod.HistoryMode.get() is expected


def test_history_mode_setup_parser() -> None:
    parser = FakeParser()

    store_mod.HistoryMode.setup_parser(parser)  # type: ignore[arg-type]

    assert len(parser.calls) == 1
    args, kwargs = parser.calls[0]
    assert args == ("--history-mode",)
    assert kwargs["choices"] == ("none", "r", "w", "rw")
    assert kwargs["command"] == "run"
    assert "none=no access" in kwargs["help"]


@pytest.mark.parametrize(
    ("raw_mode", "can_load", "can_record", "root_is_none"),
    [
        ("none", False, False, True),
        ("r", True, False, False),
        ("w", False, True, False),
        ("rw", True, True, False),
    ],
)
def test_history_store_modes_gate_load_and_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raw_mode: str,
    can_load: bool,
    can_record: bool,
    root_is_none: bool,
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", raw_mode)

    job = FakeJob(duration=99.0)
    file = seed_history(tmp_path, job, [12.5])
    before = file.read_text()

    store = RecordingStore(tmp_path)

    assert (store.root is None) is root_is_none

    loaded = store.load(job)
    if can_load:
        assert loaded is not None
        assert loaded["records"][0]["duration"] == 12.5
    else:
        assert loaded is None

    store.record(job)

    after = file.read_text()
    if can_record:
        assert after != before
        assert len([r for r in read_jsonl(file) if r.get("what") == "record"]) == 2
    else:
        assert after == before


def test_path_for_uses_job_id_sharding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "rw")
    job = FakeJob(job_id="abcdef" + "0" * 58)
    store = his.HistoryStore(tmp_path)

    assert store.path_for(job) == tmp_path / "jobs" / "ab" / f"{job.id[2:]}.jsonl"


def test_none_mode_sets_root_to_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "none")

    store = his.HistoryStore(tmp_path)

    assert store.root is None
    assert store.path_for(FakeJob()) is None


def test_load_returns_none_for_missing_history_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "rw")

    store = his.HistoryStore(tmp_path)

    assert store.load(FakeJob()) is None


def test_load_parses_meta_and_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "rw")
    job = FakeJob()
    seed_history(tmp_path, job, [10.0, 20.0])

    store = his.HistoryStore(tmp_path)
    loaded = store.load(job)

    assert loaded is not None
    assert loaded["meta"]["id"] == job.id
    assert [r["duration"] for r in loaded["records"]] == [10.0, 20.0]
    assert "what" not in loaded["meta"]
    assert all("what" not in r for r in loaded["records"])


def test_runtime_statistics_returns_none_when_read_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "w")
    job = FakeJob()
    seed_history(tmp_path, job, [10.0, 20.0])

    store = his.HistoryStore(tmp_path)

    assert store.runtime_statistics(job) is None


def test_runtime_statistics_uses_successful_durations_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "r")
    job = FakeJob()
    seed_history(
        tmp_path,
        job,
        [10.0, 999.0, None, 30.0],
        statuses=["success", "failed", "success", "success"],
    )

    store = his.HistoryStore(tmp_path)
    stats = store.runtime_statistics(job)

    assert stats is not None
    assert stats.count == 2
    assert stats.mean == 20.0
    assert stats.min == 10.0
    assert stats.max == 30.0


def test_runtime_statistics_returns_none_for_corrupt_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "rw")
    job = FakeJob()
    file = history_path(tmp_path, job)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("{not valid json\n")

    store = his.HistoryStore(tmp_path)

    assert store.runtime_statistics(job) is None


def test_estimate_runtime_ignores_history_when_read_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "w")
    job = FakeJob(timeout=300.0)
    seed_history(tmp_path, job, [10.0])

    store = his.HistoryStore(tmp_path)

    assert his.estimate_runtime(job, store=store) == 225.0


def test_estimate_runtime_uses_history_when_read_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CANARY_HISTORY_MODE", "r")
    job = FakeJob(timeout=300.0)
    seed_history(tmp_path, job, [10.0])

    store = his.HistoryStore(tmp_path)

    assert his.estimate_runtime(job, store=store) == pytest.approx(10.5)


def test_compact_keeps_recent_records_and_folds_dropped_totals(tmp_path: Path) -> None:
    job = FullFakeJob()
    path = history_path(tmp_path, job)
    path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "what": "meta",
        "version": store_mod.SCHEMA,
        "id": job.id,
        "name": job.id,
        "root": "/old",
        "path": "old.pyt",
        "parameters": {},
        "totals": {"failed": 2},
    }
    records = [
        {
            "what": "record",
            "version": store_mod.SCHEMA,
            "recorded_at": float(i),
            "status": "success",
            "duration": float(i),
            "timeout": 300.0,
            "timeout_multiplier": 1.0,
            "file_hash": "abcdefg",
            "host": "myhost",
        }
        for i in range(store_mod.KEEP + 5)
    ]
    path.write_text("".join(pyjson.dumps(r) + "\n" for r in [meta, *records]))

    store_mod.HistoryStore._compact(path, job)

    compacted = read_jsonl(path)
    compacted_meta = compacted[0]
    compacted_records = [r for r in compacted if r.get("what") == "record"]

    assert compacted_meta["what"] == "meta"
    assert compacted_meta["id"] == job.id
    assert compacted_meta["root"] == str(job.spec.file_root)
    assert compacted_meta["path"] == str(job.spec.file_path)
    assert compacted_meta["totals"]["failed"] == 2
    assert compacted_meta["totals"]["success"] == 5

    assert len(compacted_records) == store_mod.KEEP
    assert [r["duration"] for r in compacted_records] == [
        float(i) for i in range(5, store_mod.KEEP + 5)
    ]


def test_find_cache_dir_prefers_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_cache = tmp_path / "env-cache"
    monkeypatch.setenv("CANARY_CACHE_DIR", str(env_cache))
    monkeypatch.setattr(
        store_mod.config, "get", lambda *args, **kwargs: str(tmp_path / "config-cache")
    )

    assert store_mod._find_cache_dir(tmp_path) == env_cache


def test_find_cache_dir_uses_config_when_environment_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_cache = tmp_path / "config-cache"
    monkeypatch.setattr(
        store_mod.config,
        "get",
        lambda key, *args, **kwargs: str(config_cache) if key == "run:cache:dir" else None,
    )

    assert store_mod._find_cache_dir(tmp_path) == config_cache


def test_find_cache_dir_walks_to_workspace_tag(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "a" / "b"
    nested.mkdir(parents=True)
    (workspace / "WORKSPACE.TAG").write_text("")

    assert store_mod._find_cache_dir(nested) == workspace / "cache"


def test_find_cache_dir_returns_none_without_anchor(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert store_mod._find_cache_dir(nested) is None
