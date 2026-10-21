# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import _canary.api.query as query_api


class FakeDB:
    def __init__(self):
        self.connected = False
        self.closed = False
        self.results = {}
        self.history = {}
        self.session_rows = {}
        self.schema = {"tables": ["results"]}
        self.stats = {"result_count": 0}
        self.selected = [{"x": 1}]

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True

    def get_results(self):
        return self.results

    def get_results_for_session(self, session):
        return self.session_rows.get(session, [])

    def get_result_history(self, job_id):
        return self.history.get(job_id, [])

    def get_schema(self):
        return self.schema

    def get_stats(self):
        return self.stats

    def select(self, statement):
        if not statement.lower().strip().startswith("select"):
            raise ValueError("only SELECT")
        return self.selected


class FakeWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.sessions_dir = root / "sessions"
        self.refs_dir = root / "refs"
        self.db = FakeDB()
        self._jobs = {}

        self.sessions_dir.mkdir(parents=True)
        self.refs_dir.mkdir(parents=True)

    def find_job(self, job_id):
        return self._jobs[job_id]


@pytest.fixture
def workspace(tmp_path):
    return FakeWorkspace(tmp_path)


def patch_workspace(query_api, monkeypatch, workspace):
    monkeypatch.setattr(query_api.Workspace, "load", lambda: workspace)


def patch_converter(query_api, monkeypatch):
    def convert(workspace, row):
        return {
            "id": row["id"],
            "name": row["spec_name"],
            "fullname": row.get("spec_fullname", row["spec_name"]),
            "file_path": row.get("file_path", ""),
            "exec_dir": str(workspace.sessions_dir / row["session"] / row.get("workspace", "w")),
            "session": row["session"],
            "exit_code": row.get("exit_code", 0),
            "status": {
                "category": row["category"],
                "outcome": row["outcome"],
                "reason": row.get("reason"),
            },
            "timings": row.get(
                "timings",
                {"pending": -1, "setup": -1, "running": 1.0, "teardown": -1, "total": 2.0},
            ),
            "started_at": None,
            "stopped_at": None,
            "last_activity": None,
        }

    monkeypatch.setattr(query_api._query_cmd, "_row_to_job_entry", convert)


def patch_session_resolver(query_api, monkeypatch):
    def resolve(workspace, session):
        if session == "latest":
            latest = workspace.refs_dir / "latest"
            if latest.exists():
                return workspace.sessions_dir / latest.read_text().strip()
            return workspace.sessions_dir / "latest"
        return workspace.sessions_dir / session

    monkeypatch.setattr(query_api._query_cmd, "_resolve_session_dir", resolve)


def write_session(workspace, name, **data):
    path = workspace.sessions_dir / name
    path.mkdir(exist_ok=True)
    payload = {"name": name, **data}
    (path / "session.lock").write_text(json.dumps(payload))
    return path


def row(
    id, name, *, session="s1", category="PASS", outcome="PASSED", measurements=None, timings=None
):
    data = {
        "id": id,
        "spec_name": name,
        "spec_fullname": f"suite/{name}",
        "session": session,
        "workspace": f"w_{name}",
        "category": category,
        "outcome": outcome,
    }
    if measurements is not None:
        data["measurements"] = measurements
    if timings is not None:
        data["timings"] = timings
    return data


def test_latest_session_returns_resolved_session_name(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)

    write_session(workspace, "s1", returncode=0)
    (workspace.refs_dir / "latest").write_text("s1")

    assert query_api.latest_session() == "s1"


def test_session_returns_metadata_and_summary(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(
        workspace,
        "s1",
        started_on="start",
        finished_on="finish",
        returncode=0,
        argv=["canary", "run"],
    )
    workspace.db.session_rows["s1"] = [
        row("1", "pass", session="s1", category="PASS", outcome="PASSED"),
        row("2", "fail", session="s1", category="FAIL", outcome="FAILED"),
    ]

    out = query_api.session("s1")

    assert out["name"] == "s1"
    assert out["started_on"] == "start"
    assert out["finished_on"] == "finish"
    assert out["returncode"] == 0
    assert out["argv"] == ["canary", "run"]
    assert out["summary"]["total"] == 2
    assert out["summary"]["passed"] == 1
    assert out["summary"]["failed"] == 1
    assert out["summary"]["ok"] is False


def test_sessions_filters_by_returncode_ok_and_name(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(workspace, "nightly_pass", returncode=0)
    write_session(workspace, "nightly_fail", returncode=1)
    write_session(workspace, "manual_fail", returncode=1)

    workspace.db.session_rows["nightly_pass"] = [
        row("1", "a", session="nightly_pass", category="PASS", outcome="PASSED")
    ]
    workspace.db.session_rows["nightly_fail"] = [
        row("2", "b", session="nightly_fail", category="FAIL", outcome="FAILED")
    ]
    workspace.db.session_rows["manual_fail"] = [
        row("3", "c", session="manual_fail", category="FAIL", outcome="FAILED")
    ]

    assert [s["name"] for s in query_api.sessions(returncode=1)] == ["manual_fail", "nightly_fail"]
    assert [s["name"] for s in query_api.sessions(ok=True)] == ["nightly_pass"]
    assert [s["name"] for s in query_api.sessions(ok=False, name_contains="nightly")] == [
        "nightly_fail"
    ]


def test_jobs_defaults_to_latest_session(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(workspace, "s1")
    (workspace.refs_dir / "latest").write_text("s1")

    workspace.db.session_rows["s1"] = [
        row("b", "b_test", session="s1", category="PASS", outcome="PASSED"),
        row("a", "a_test", session="s1", category="FAIL", outcome="FAILED"),
    ]

    out = query_api.jobs()

    assert [entry["name"] for entry in out] == ["a_test", "b_test"]
    assert out[0]["failed"] is True
    assert out[1]["passed"] is True


def test_jobs_session_none_uses_latest_run_per_job_across_all_sessions(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_converter(query_api, monkeypatch)

    workspace.db.results = {
        "2": row("2", "b", session="s2", category="PASS", outcome="PASSED"),
        "1": row("1", "a", session="s1", category="FAIL", outcome="FAILED"),
    }

    out = query_api.jobs(session=None)

    assert workspace.db.connected is True
    assert workspace.db.closed is True
    assert [entry["name"] for entry in out] == ["a", "b"]


def test_jobs_filters_semantically(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(workspace, "s1")
    workspace.db.session_rows["s1"] = [
        row("1", "pass_case", category="PASS", outcome="PASSED"),
        row("2", "fail_case", category="FAIL", outcome="FAILED"),
        row("3", "timeout_case", category="FAIL", outcome="TIMEOUT"),
        row("4", "diff_case", category="FAIL", outcome="DIFFED"),
        row("5", "skip_case", category="SKIP", outcome="SKIPPED"),
        row("6", "cancel_case", category="CANCEL", outcome="CANCELLED"),
        row("7", "unfinished_case", category="NONE", outcome="NONE"),
    ]

    assert [j["name"] for j in query_api.passed_jobs("s1")] == ["pass_case"]
    assert [j["name"] for j in query_api.failed_jobs("s1")] == ["fail_case"]
    assert [j["name"] for j in query_api.timeout_jobs("s1")] == ["timeout_case"]
    assert [j["name"] for j in query_api.diffed_jobs("s1")] == ["diff_case"]
    assert [j["name"] for j in query_api.skipped_jobs("s1")] == ["skip_case"]
    assert [j["name"] for j in query_api.cancelled_jobs("s1")] == ["cancel_case"]
    assert [j["name"] for j in query_api.unfinished_jobs("s1")] == ["unfinished_case"]

    assert [j["name"] for j in query_api.jobs(session="s1", name_contains="case")] == [
        "cancel_case",
        "diff_case",
        "fail_case",
        "pass_case",
        "skip_case",
        "timeout_case",
        "unfinished_case",
    ]

    assert [j["name"] for j in query_api.jobs(session="s1", nonpassing=True)] == [
        "cancel_case",
        "diff_case",
        "fail_case",
        "skip_case",
        "timeout_case",
        "unfinished_case",
    ]


def test_jobs_filters_by_duration_and_sorting(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(workspace, "s1")
    workspace.db.session_rows["s1"] = [
        row(
            "1",
            "fast",
            timings={"pending": -1, "setup": -1, "running": 1.0, "teardown": -1, "total": 2.0},
        ),
        row(
            "2",
            "slow",
            timings={"pending": -1, "setup": -1, "running": 10.0, "teardown": -1, "total": 11.0},
        ),
    ]

    assert [j["name"] for j in query_api.jobs(session="s1", duration_gt=5)] == ["slow"]
    assert [j["name"] for j in query_api.jobs(session="s1", sort_by="duration", reverse=True)] == [
        "slow",
        "fast",
    ]


def test_job_returns_latest_history_entry(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_converter(query_api, monkeypatch)

    workspace._jobs["abc"] = SimpleNamespace(id="full-id")
    workspace.db.history["full-id"] = [
        row("full-id", "old", session="s1", category="FAIL", outcome="FAILED"),
        row("full-id", "new", session="s2", category="PASS", outcome="PASSED"),
    ]

    out = query_api.job("abc")

    assert workspace.db.connected is True
    assert workspace.db.closed is True
    assert out["name"] == "new"
    assert out["passed"] is True


def test_job_raises_when_no_history(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)

    workspace._jobs["abc"] = SimpleNamespace(id="full-id")
    workspace.db.history["full-id"] = []

    with pytest.raises(ValueError, match="No run history"):
        query_api.job("abc")


def test_job_history_returns_all_runs(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_converter(query_api, monkeypatch)

    workspace._jobs["abc"] = SimpleNamespace(id="full-id")
    workspace.db.history["full-id"] = [
        row("full-id", "old", session="s1", category="FAIL", outcome="FAILED"),
        row("full-id", "new", session="s2", category="PASS", outcome="PASSED"),
    ]

    out = query_api.job_history("abc")

    assert [entry["name"] for entry in out] == ["old", "new"]


def test_measurement_table_uses_measurements_from_db_rows(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(workspace, "s1")
    workspace.db.session_rows["s1"] = [
        row(
            "1",
            "case_a",
            measurements={"runtime": 2.5, "iters": 10},
            category="PASS",
            outcome="PASSED",
        ),
        row(
            "2",
            "case_b",
            measurements=json.dumps({"runtime": 5.0}),
            category="FAIL",
            outcome="FAILED",
        ),
    ]

    assert query_api.measurement_table(session="s1", key="runtime") == [
        {
            "id": "1",
            "name": "case_a",
            "fullname": "suite/case_a",
            "session": "s1",
            "key": "runtime",
            "value": 2.5,
            "status": {"category": "PASS", "outcome": "PASSED", "reason": None},
        },
        {
            "id": "2",
            "name": "case_b",
            "fullname": "suite/case_b",
            "session": "s1",
            "key": "runtime",
            "value": 5.0,
            "status": {"category": "FAIL", "outcome": "FAILED", "reason": None},
        },
    ]

    all_rows = query_api.measurement_table(session="s1", include_status=False)
    assert [item["key"] for item in all_rows] == ["iters", "runtime", "runtime"]
    assert "status" not in all_rows[0]


def test_measurements_and_measurement_read_job_lock(workspace, monkeypatch, tmp_path):
    patch_workspace(query_api, monkeypatch, workspace)

    jobdir = tmp_path / "job"
    jobdir.mkdir()
    lockfile = jobdir / "testcase.lock"
    lockfile.write_text(json.dumps({"measurements": {"runtime": 3.5, "iters": 12}}))

    monkeypatch.setattr(query_api._query_cmd, "_job_lockfile", lambda ws, jobid: lockfile)

    assert query_api.measurements("abc") == {"runtime": 3.5, "iters": 12}
    assert query_api.measurement("abc", "runtime") == 3.5
    assert query_api.measurement("abc", "missing", default="x") == "x"


def test_environment_reads_env_json(workspace, monkeypatch, tmp_path):
    patch_workspace(query_api, monkeypatch, workspace)

    jobdir = tmp_path / "job"
    jobdir.mkdir()
    lockfile = jobdir / "testcase.lock"
    lockfile.write_text("{}")
    (jobdir / "env.json").write_text(json.dumps({"CUDA_VISIBLE_DEVICES": "0", "PATH": "/bin"}))

    monkeypatch.setattr(query_api._query_cmd, "_job_lockfile", lambda ws, jobid: lockfile)

    assert query_api.environment("abc") == {"CUDA_VISIBLE_DEVICES": "0", "PATH": "/bin"}
    assert query_api.environment("abc", "CUDA_VISIBLE_DEVICES") == "0"
    assert query_api.environment("abc", "MISSING", default="unset") == "unset"


def test_environment_missing_env_json_raises(workspace, monkeypatch, tmp_path):
    patch_workspace(query_api, monkeypatch, workspace)

    jobdir = tmp_path / "job"
    jobdir.mkdir()
    lockfile = jobdir / "testcase.lock"
    lockfile.write_text("{}")

    monkeypatch.setattr(query_api._query_cmd, "_job_lockfile", lambda ws, jobid: lockfile)

    with pytest.raises(FileNotFoundError):
        query_api.environment("abc")


def test_cache_reads_cache_file(workspace, monkeypatch, tmp_path):
    patch_workspace(query_api, monkeypatch, workspace)

    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps({"hits": 3}))

    job = SimpleNamespace(id="abc")
    workspace._jobs["abc"] = job

    monkeypatch.setattr(query_api._query_cmd, "_find_cache_path", lambda found: cache_file)

    assert query_api.cache("abc") == {"hits": 3}


def test_cache_missing_raises(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)

    job = SimpleNamespace(id="abc")
    workspace._jobs["abc"] = job

    monkeypatch.setattr(query_api._query_cmd, "_find_cache_path", lambda found: None)

    with pytest.raises(FileNotFoundError, match="No cache entry"):
        query_api.cache("abc")


def test_raw_job_lock_value_and_keys(workspace, monkeypatch, tmp_path):
    patch_workspace(query_api, monkeypatch, workspace)

    lockfile = tmp_path / "testcase.lock"
    lockfile.write_text(
        json.dumps(
            {
                "name": "case_a",
                "status": {"__type__": "Outcome", "value": "PASSED"},
                "measurements": {"runtime": 1.2},
            }
        )
    )

    monkeypatch.setattr(query_api._query_cmd, "_job_lockfile", lambda ws, jobid: lockfile)

    assert query_api.raw_job_lock("abc")["name"] == "case_a"
    assert query_api.raw_job_value("abc", "measurements.runtime") == 1.2
    assert query_api.raw_job_value("abc", "status", clean=True) == "PASSED"
    assert query_api.raw_job_value("abc", "status", clean=False) == {
        "__type__": "Outcome",
        "value": "PASSED",
    }

    # list_json_object_paths returns immediate children under the requested path.
    assert set(query_api.raw_job_keys("abc", ".")) == {"name", "measurements", "status"}

    # Query nested paths by asking for keys under that object.
    assert query_api.raw_job_keys("abc", "measurements") == ["runtime"]


def test_raw_session_lock_value_and_keys(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)

    write_session(workspace, "s1", returncode=0, nested={"value": 42})

    assert query_api.raw_session_lock("s1")["name"] == "s1"
    assert query_api.raw_session_value("s1", "nested.value") == 42

    assert set(query_api.raw_session_keys("s1", ".")) == {"name", "returncode", "nested"}
    assert query_api.raw_session_keys("s1", "nested") == ["value"]


def test_db_helpers(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)

    assert query_api.db_schema() == {"tables": ["results"]}
    assert query_api.db_stats() == {"result_count": 0}
    assert query_api.sql("SELECT * FROM results") == [{"x": 1}]
    assert query_api.sql(["SELECT", "*", "FROM", "results"]) == [{"x": 1}]


def test_sql_rejects_non_select(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)

    with pytest.raises(ValueError, match="only permits SELECT"):
        query_api.sql("DELETE FROM results")


def test_invalid_sort_key_raises(workspace, monkeypatch):
    patch_workspace(query_api, monkeypatch, workspace)
    patch_session_resolver(query_api, monkeypatch)
    patch_converter(query_api, monkeypatch)

    write_session(workspace, "s1")
    workspace.db.session_rows["s1"] = []

    with pytest.raises(ValueError, match="invalid sort key"):
        query_api.jobs(session="s1", sort_by="bogus")
