# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
from types import SimpleNamespace

import pytest

from _canary.subcommands import query as query_mod
from _canary.subcommands.query import Query
from _canary.subcommands.query import load_capability_dataset
from _canary.subcommands.query import query_capabilities
from _canary.subcommands.query import query_json


def namespace(**kwargs):
    defaults = {"jobid": None, "session": None, "capability": None, "query": ".", "terse": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_load_capabilities_database():
    data = load_capability_dataset()
    assert data["dataset"] == "capabilities"
    assert "overview" in data
    assert "hooks" in data
    assert "post" in data["hooks"]


def test_query_capabilities_all_shortcut(capsys):
    rc = Query().execute(namespace(capability="all"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dataset"] == "capabilities"
    assert out["schema_version"]
    assert "overview" in out


def test_query_capabilities_dataset_name_still_prints_whole_database(capsys):
    rc = Query().execute(namespace(capability="capabilities"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dataset"] == "capabilities"
    assert "overview" in out


def test_query_capabilities_dataset_name_with_explicit_query(capsys):
    rc = Query().execute(namespace(capability="capabilities", query=".overview"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "what_is_canary" in out
    assert "major_concepts" in out


def test_query_capabilities_overview_shortcut(capsys):
    rc = Query().execute(namespace(capability="overview"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "what_is_canary" in out
    assert "major_concepts" in out


def test_query_capabilities_nested_shortcut(capsys):
    rc = Query().execute(namespace(capability="hooks.post"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "canary_runtest_finish" in out


def test_query_capabilities_shortcut_plus_query_suffix(capsys):
    rc = Query().execute(namespace(capability="hooks", query=".post.canary_runtest_finish.purpose"))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "after" in out.lower()
    assert "test" in out.lower()


def test_query_capabilities_missing_shortcut_reports_available_keys():
    with pytest.raises(KeyError) as exc:
        query_capabilities("does_not_exist")

    message = str(exc.value)
    assert "does_not_exist" in message
    assert "Available keys" in message
    assert "overview" in message


def test_query_json_existing_dot_semantics_are_preserved():
    data = {"measurements": {"data": {"max_stress": 12.5}}, "items": [{"name": "a"}]}

    assert query_json(data, ".") == data
    assert query_json(data, "measurements") == {"data": {"max_stress": 12.5}}
    assert query_json(data, ".measurements.data.max_stress") == 12.5
    assert query_json(data, ".items[0].name") == "a"


def test_query_job_existing_behavior_is_preserved(tmp_path, monkeypatch, capsys):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    lockfile = job_dir / "testcase.lock"
    lockfile.write_text(
        json.dumps(
            {
                "id": "abc123",
                "measurements": {"data": {"answer": 42}},
                "status": {"outcome": "SUCCESS"},
            }
        )
    )

    class FakeWorkspace:
        @staticmethod
        def load():
            return FakeWorkspace()

        def find_job(self, jobid):
            assert jobid == "abc123"
            return SimpleNamespace(lockfile=lockfile)

    monkeypatch.setattr(query_mod, "Workspace", FakeWorkspace)

    rc = Query().execute(namespace(jobid="abc123", query="."))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "abc123"

    rc = Query().execute(namespace(jobid="abc123", query=".measurements"))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"data": {"answer": 42}}


def test_query_session_existing_behavior_is_preserved(tmp_path, monkeypatch, capsys):
    refs_dir = tmp_path / "refs"
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "session-001"
    refs_dir.mkdir()
    session_dir.mkdir(parents=True)

    (session_dir / "session.lock").write_text(
        json.dumps(
            {
                "name": "session-001",
                "job_ids": ["abc123"],
                "measurements": {"campaign": "agentic-demo"},
            }
        )
    )

    (refs_dir / "latest").write_text("../sessions/session-001")

    class FakeWorkspace:
        def __init__(self):
            self.refs_dir = refs_dir
            self.sessions_dir = sessions_dir

        @staticmethod
        def load():
            return FakeWorkspace()

    monkeypatch.setattr(query_mod, "Workspace", FakeWorkspace)

    rc = Query().execute(namespace(session="session-001", query="."))

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["name"] == "session-001"

    rc = Query().execute(namespace(session="latest", query=".measurements.campaign"))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == "agentic-demo"
