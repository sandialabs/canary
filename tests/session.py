# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import datetime
from pathlib import Path
from typing import Any
from typing import cast

from _canary.job import Measurements
from _canary.util import json_helper as json
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


def test_session_serialize_stores_job_ids_not_jobs(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.returncode = 0
    session.started_on = datetime.datetime(2026, 8, 20, 12, 0, 0)
    session.finished_on = datetime.datetime(2026, 8, 20, 12, 1, 30)
    session.add_measurement("workflow", "agentic")

    data = session.__serialize__()

    assert data["name"] == "session-1"
    assert data["prefix"] == str(tmp_path / "sessions" / "session-1")
    assert data["job_ids"] == ["a" * 64, "b" * 64]
    assert "jobs" not in data

    assert data["returncode"] == 0
    assert data["started_on"] == "2026-08-20T12:00:00"
    assert data["finished_on"] == "2026-08-20T12:01:30"
    assert isinstance(data["measurements"], Measurements)
    assert data["measurements"].data["workflow"] == "agentic"


def test_session_deserialize_roundtrip_direct_dict(tmp_path: Path) -> None:
    data = {
        "name": "session-1",
        "prefix": str(tmp_path / "sessions" / "session-1"),
        "job_ids": ["a" * 64, "b" * 64],
        "returncode": 7,
        "started_on": "2026-08-20T12:00:00",
        "finished_on": "2026-08-20T12:01:30",
        "measurements": Measurements(data={"agent": "sandi", "attempts": 3}),
    }

    session = Session.__deserialize__(data)

    assert session.name == "session-1"
    assert session.jobs == []
    assert session.job_ids == ["a" * 64, "b" * 64]
    assert session.prefix == tmp_path / "sessions" / "session-1"
    assert session.returncode == 7
    assert session.started_on == datetime.datetime(2026, 8, 20, 12, 0, 0)
    assert session.finished_on == datetime.datetime(2026, 8, 20, 12, 1, 30)
    assert session.measurements.data == {"agent": "sandi", "attempts": 3}


def test_session_json_roundtrip(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.returncode = 0
    session.started_on = datetime.datetime(2026, 8, 20, 12, 0, 0)
    session.finished_on = datetime.datetime(2026, 8, 20, 12, 1, 30)
    session.add_measurement("agent", {"name": "sandi"})

    text = json.dumps(session)
    out = json.loads(text)

    assert isinstance(out, Session)
    assert out.name == session.name
    assert out.jobs == []
    assert out.job_ids == session.job_ids
    assert out.prefix == session.prefix
    assert out.returncode == 0
    assert out.started_on == session.started_on
    assert out.finished_on == session.finished_on
    assert out.measurements.data == {"agent": {"name": "sandi"}}


def test_session_save_writes_session_lock(tmp_path: Path) -> None:
    session = make_session(tmp_path)
    session.returncode = 3
    session.started_on = datetime.datetime(2026, 8, 20, 12, 0, 0)
    session.finished_on = datetime.datetime(2026, 8, 20, 12, 1, 30)
    session.add_measurement("scheduler", {"queue_wait": 12.5})

    session.save()

    lockfile = session.prefix / "session.lock"
    assert lockfile.exists()

    out = json.loads(lockfile.read_text())

    assert isinstance(out, Session)
    assert out.name == "session-1"
    assert out.jobs == []
    assert out.job_ids == ["a" * 64, "b" * 64]
    assert out.returncode == 3
    assert out.measurements.data["scheduler"] == {"queue_wait": 12.5}


def test_session_save_creates_prefix_directory(tmp_path: Path) -> None:
    session = make_session(tmp_path)

    assert not session.prefix.exists()

    session.save()

    assert session.prefix.exists()
    assert (session.prefix / "session.lock").exists()
