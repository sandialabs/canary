# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The read endpoints, through accept(), on a workspace with a finished run."""

import json
import subprocess
import sys
import uuid

import pytest

from _canary.api.dispatch import accept

PASSING = 'import sys\nif __name__ == "__main__":\n    sys.exit(0)\n'
FAILING = 'import sys\nif __name__ == "__main__":\n    sys.exit(1)\n'


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    """A workspace whose one session ran ok/ok.pyt (passes) and failing/failing.pyt."""
    anchor = tmp_path_factory.mktemp("ws")
    for name, body in (("ok", PASSING), ("failing", FAILING)):
        (anchor / name).mkdir()
        (anchor / name / f"{name}.pyt").write_text(body)
    run = subprocess.run(
        [sys.executable, "-m", "canary", "run", "ok", "failing"],
        cwd=anchor,
        capture_output=True,
        text=True,
    )
    assert run.returncode != 0 and (anchor / ".canary").is_dir(), run.stderr
    return anchor / ".canary"


@pytest.fixture
def get(root):
    def get(path, **body):
        result = accept(
            f"q{uuid.uuid4().hex}", {"path": path, "request": body}, user="u", workspace_root=root
        )
        assert result is not None
        return result

    return get


def _done(result):
    assert (result.status_code, result.state) == (200, "done"), result.error
    return result.data


def test_status_lists_every_job_with_paths_relative_to_the_anchor(root, get):
    views = _done(get("/canary/status"))
    assert sorted(v["name"] for v in views) == ["failing", "ok"]
    # canary's own paths: file_path is relative to file_root (published relative to the
    # workspace, as the scan roots ok/ and failing/ are in it)
    assert {(v["file_root"], v["file_path"]) for v in views} == {
        ("ok", "ok.pyt"),
        ("failing", "failing.pyt"),
    }
    assert {v["name"]: v["status"]["category"] for v in views} == {"ok": "PASS", "failing": "FAIL"}


def test_no_result_carries_the_servers_absolute_paths(root, get):
    for path in ("/canary/status", "/canary/query/jobs", "/canary/query/failures"):
        assert str(root.parent) not in get(path).model_dump_json()


def test_sessions_and_latest(get):
    sessions = _done(get("/canary/query/sessions"))
    assert len(sessions) == 1 and sessions[0]["job_count"] == 2
    name = sessions[0]["name"]
    session = _done(get("/canary/query/session/latest"))
    assert session["session_id"] == name and session["result_count"] == 2
    assert sorted(j["name"] for j in session["jobs"]) == ["failing", "ok"]
    assert session["argv"] and "returncode" in session  # from session.lock
    assert _done(get(f"/canary/query/session/{name}/outcome_counts")) == session["outcome_counts"]
    assert _done(get("/canary/query/session/latest/jobs/0/name")) == session["jobs"][0]["name"]


def test_failures_are_the_sessions_failed_jobs(get):
    assert [v["name"] for v in _done(get("/canary/query/failures"))] == ["failing"]


def test_failures_can_carry_the_end_of_each_jobs_log(get):
    (plain,) = _done(get("/canary/query/failures"))
    assert "log_tail" not in plain
    (failing,) = _done(get("/canary/query/failures", log_tail=3))
    log = _done(get("/canary/query/job/failing/log", tail=3))
    assert failing["log_tail"] == log["text"] and failing["log_tail"]


def test_jobs_by_session(get):
    session = _done(get("/canary/query/sessions"))[0]["name"]
    assert len(_done(get("/canary/query/jobs", session_id=session))) == 2


def test_job(get):
    job_id = next(v["id"] for v in _done(get("/canary/status")) if v["name"] == "ok")
    job = _done(get(f"/canary/query/job/{job_id}"))
    assert job["status"]["category"] == "PASS"
    assert job["spec"]["id"] == job_id and "measurements" in job and "env" not in job
    assert get(f"/canary/query/job/{'0' * 12}").status_code == 404
    assert _done(get("/canary/query/job/ok"))["id"] == job_id  # by name
    assert _done(get(f"/canary/query/job/{job_id[:8]}"))["id"] == job_id
    for wildcard in ("%", "_"):  # no SQL LIKE patterns: these match no job
        assert get(f"/canary/query/job/{wildcard}").status_code == 404
    assert get("/canary/query/job/").status_code == 404  # no such route
    assert _done(get("/canary/query/job/ok", session_id="latest"))["id"] == job_id
    assert get("/canary/query/job/ok", job_id="ok").status_code == 400  # the route has it


def test_job_paths_select_part_of_the_job(get):
    job = _done(get("/canary/query/job/ok"))
    assert _done(get("/canary/query/job/ok/spec/id")) == job["id"]
    assert _done(get("/canary/query/job/ok/measurements")) == job["measurements"]
    assert _done(get("/canary/query/job/ok/status/category")) == "PASS"
    assert isinstance(_done(get("/canary/query/job/ok/env")), dict)  # env.json, on request
    missing = get("/canary/query/job/ok/measurements/nope")
    assert missing.status_code == 404 and "no 'nope' at measurements" in (missing.error or "")


def test_job_log_returns_what_the_job_printed(root, get):
    log = _done(get("/canary/query/job/failing/log"))
    assert log["path"].endswith("canary-out.txt") and (root.parent / log["path"]).is_file()
    assert log["text"] == (root.parent / log["path"]).read_text() and log["lines"] > 1
    tail = _done(get("/canary/query/job/failing/log", tail=1))
    assert tail["text"].count("\n") <= 1 and tail["lines"] == log["lines"]
    assert _done(get("/canary/query/job/failing/log", session_id="latest")) == log
    assert get("/canary/query/job/failing/log", stream="stderr").status_code == 404
    assert get("/canary/query/job/nope/log").status_code == 404


def test_job_records_carry_measurements(get):
    for path in ("/canary/status", "/canary/query/jobs", "/canary/query/failures"):
        assert all(isinstance(v["measurements"], dict) for v in _done(get(path))), path


def test_location_gives_a_jobs_paths_relative_to_the_workspace(root, get):
    where = _done(get("/canary/location/ok"))
    assert where["input"] == "ok/ok.pyt" and where["source_dir"] == "ok"
    assert where["log"].startswith(where["exec_dir"]) and where["log"].endswith(".txt")
    assert (root.parent / where["log"]).is_file()
    assert get("/canary/location/nope").status_code == 404


def test_status_of_named_jobs(get):
    assert [v["name"] for v in _done(get("/canary/status", spec_ids=["ok"]))] == ["ok"]
    assert get("/canary/status", spec_ids=["nope"]).status_code == 404
    assert get("/canary/status", spec_ids=[]).status_code == 400  # omit it for every job


def test_unknown_sessions_are_404(get):
    for path, body in (
        ("/canary/query/session/nope", {}),
        ("/canary/query/failures", {"session_id": "nope"}),
        ("/canary/query/jobs", {"session_id": "nope"}),
    ):
        result = get(path, **body)
        assert (result.status_code, result.state) == (404, "rejected"), path


def test_db_selects_capped_and_refuses_anything_else(get, monkeypatch):
    from _canary.api import query

    data = _done(get("/canary/query/db", sql="SELECT spec_name FROM results ORDER BY spec_name"))
    assert data == {"rows": [{"spec_name": "failing"}, {"spec_name": "ok"}], "truncated": False}
    monkeypatch.setattr(query, "MAX_ROWS", 1)
    assert _done(get("/canary/query/db", sql="SELECT * FROM results"))["truncated"] is True
    assert get("/canary/query/db", sql="DELETE FROM results").status_code == 400
    assert get("/canary/query/db", sql="SELECT nonsense FROM nowhere").status_code == 400
    assert len(_done(get("/canary/query/db", sql="SELECT * FROM results"))["rows"]) == 1


def test_db_publishes_absolute_paths(root, get):
    data = _done(get("/canary/query/db", sql="SELECT file_root, workspace FROM results"))
    assert {row["file_root"] for row in data["rows"]} == {"ok", "failing"}
    assert str(root.parent) not in json.dumps(data)


def test_db_schema_lists_tables_and_columns(get):
    tables = _done(get("/canary/query/db/schema"))
    assert {"results", "specs"} <= set(tables)
    columns = _done(get("/canary/query/db/schema/results/columns"))
    assert {"spec_name", "session", "measurements"} <= {c["name"] for c in columns}
    assert tables["results"]["sql"].startswith("CREATE TABLE results")
    assert get("/canary/query/db/schema/nope").status_code == 404


def test_db_stats(get):
    stats = _done(get("/canary/query/db/stats"))
    assert stats["result_count"] == 2 and stats["session_count"] == 1


def test_db_params_and_json_columns(get):
    sql = "SELECT spec_name, measurements, timekeeper FROM results WHERE spec_name = ?"
    raw = _done(get("/canary/query/db", sql=sql, params=["ok"]))["rows"]
    assert [r["spec_name"] for r in raw] == ["ok"] and isinstance(raw[0]["measurements"], str)
    (row,) = _done(get("/canary/query/db", sql=sql, params=["ok"], parse_json=True))["rows"]
    assert "duration" in row["measurements"] and "data" not in row["measurements"]
    assert isinstance(row["timekeeper"], dict)


def test_db_sql_errors_point_at_the_schema(get):
    result = get("/canary/query/db", sql="SELECT duration FROM results")
    assert result.status_code == 400 and "/canary/query/db/schema" in (result.error or "")


def test_schema_describes_every_endpoint(get):
    data = _done(get("/canary/schema"))
    assert data["endpoints"]["/canary/run"]["lane"] == "work"
    assert "pathspec" in data["endpoints"]["/canary/run"]["request"]["properties"]
    assert data["endpoints"]["/canary/status"]["lane"] == "read"
    assert set(data) == {"envelope", "result", "endpoints"}
    json.dumps(data)


def test_learn_returns_what_canary_learn_prints(get):
    from _canary.app import learn

    caps = _done(get("/canary/learn/capabilities", topic="ext.pyt.parameters"))
    assert caps == learn.capabilities("ext.pyt.parameters") and "runtime_access" in caps
    assert "pyt" in _done(get("/canary/learn/capabilities", list_keys=True))
    skill = _done(get("/canary/learn/skills", topic="pyt.canary-pyt-authoring"))
    assert "canary.get_instance()" in skill["body"]
    assert "pyt.canary-pyt-authoring" in _done(get("/canary/learn/skills", list_keys=True))


def test_learn_unknown_topic_is_404(get):
    for path in ("/canary/learn/capabilities", "/canary/learn/skills"):
        result = get(path, topic="no.such.topic")
        assert result.status_code == 404 and "list_keys" in (result.error or ""), result
