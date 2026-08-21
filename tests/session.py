# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
from pathlib import Path
from typing import Any
from typing import cast

from _canary.workspace import Session


class DummyJob:
    def __init__(self, id: str, *, mask: Any = None) -> None:
        self.id = id
        self.mask = mask


def make_session(tmp_path: Path) -> Session:
    jobs = [DummyJob("a" * 64), DummyJob("b" * 64)]
    session = Session(
        name="session-1", jobs=cast(Any, jobs), prefix=tmp_path / "sessions" / "session-1"
    )
    return session


def test_session_post_init_records_job_ids(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    assert session.job_ids == ["a" * 64, "b" * 64]


def test_session_add_measurement(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    session.add_measurement("agent", {"name": "planner", "version": "1"})
    session.add_measurement("score", 42)

    assert session.measurements.data["agent"] == {"name": "planner", "version": "1"}
    assert session.measurements.data["score"] == 42


def test_session_to_lock_data_stores_job_ids_not_jobs(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.returncode = 0
    session.started_on = datetime.datetime(2026, 8, 20, 12, 0, 0)
    session.finished_on = datetime.datetime(2026, 8, 20, 12, 1, 30)
    session.add_measurement("workflow", "agentic")

    data = session.to_lock_data()

    assert data["name"] == "session-1"
    assert data["prefix"] == str(tmp_path / "sessions" / "session-1")
    assert data["job_ids"] == ["a" * 64, "b" * 64]
    assert "jobs" not in data

    assert data["returncode"] == 0
    assert data["started_on"] == "2026-08-20T12:00:00"
    assert data["finished_on"] == "2026-08-20T12:01:30"
    assert data["measurements"] == {"workflow": "agentic"}


def test_session_to_lock_data_includes_argv_and_config(tmp_path: Path, monkeypatch) -> None:
    session = make_session(tmp_path)

    monkeypatch.setattr("sys.argv", ["canary", "run", "default"])

    data = session.to_lock_data()

    assert data["argv"] == ["canary", "run", "default"]
    assert "config" in data
    assert isinstance(data["config"], dict)


def test_session_save_writes_plain_json_manifest(tmp_path: Path) -> None:
    import json

    session = make_session(tmp_path)
    session.returncode = 3
    session.started_on = datetime.datetime(2026, 8, 20, 12, 0, 0)
    session.finished_on = datetime.datetime(2026, 8, 20, 12, 1, 30)
    session.add_measurement("scheduler", {"queue_wait": 12.5})

    session.save()

    lockfile = session.prefix / "session.lock"
    assert lockfile.exists()

    data = json.loads(lockfile.read_text())

    assert data["name"] == "session-1"
    assert data["job_ids"] == ["a" * 64, "b" * 64]
    assert data["returncode"] == 3
    assert data["started_on"] == "2026-08-20T12:00:00"
    assert data["finished_on"] == "2026-08-20T12:01:30"
    assert data["measurements"]["scheduler"] == {"queue_wait": 12.5}
    assert "config" in data
    assert "argv" in data
    assert "__type__" not in data


def test_session_save_creates_prefix_directory(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    assert not session.prefix.exists()

    session.save()

    assert session.prefix.exists()
    assert (session.prefix / "session.lock").exists()


def test_session_load_lock_data_from_file(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.returncode = 9
    session.add_measurement("agent", "sandi")
    session.save()

    data = Session.load_lock_data(session.prefix / "session.lock")

    assert data["name"] == "session-1"
    assert data["returncode"] == 9
    assert data["measurements"]["agent"] == "sandi"


def test_session_load_lock_data_from_directory(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.returncode = 4
    session.save()

    data = Session.load_lock_data(session.prefix)

    assert data["name"] == "session-1"
    assert data["returncode"] == 4
