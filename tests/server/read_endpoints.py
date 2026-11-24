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
    assert len(sessions) == 1 and sessions == sorted(sessions)
    session = _done(get("/canary/query/session", expand_jobs=True))
    assert session["session_id"] == sessions[0] and session["result_count"] == 2
    assert sorted(j["name"] for j in session["jobs"]) == ["failing", "ok"]
    assert "jobs" not in _done(get("/canary/query/session", session_id=sessions[0]))


def test_failures_are_the_sessions_failed_jobs(get):
    assert [v["name"] for v in _done(get("/canary/query/failures"))] == ["failing"]


def test_jobs_by_session(get):
    session = _done(get("/canary/query/sessions"))[0]
    assert len(_done(get("/canary/query/jobs", session_id=session))) == 2


def test_job(get):
    job_id = next(v["id"] for v in _done(get("/canary/status")) if v["name"] == "ok")
    assert _done(get("/canary/query/job", job_id=job_id))["status"]["category"] == "PASS"
    assert get("/canary/query/job", job_id="0" * 12).status_code == 404
    assert _done(get("/canary/query/job", job_id="ok"))["id"] == job_id  # by name
    assert _done(get("/canary/query/job", job_id=job_id[:8]))["id"] == job_id
    for wildcard in ("%", "_"):  # no SQL LIKE patterns: these match no job
        assert get("/canary/query/job", job_id=wildcard).status_code == 404
    assert get("/canary/query/job", job_id="").status_code == 400


def test_status_of_named_jobs(get):
    assert [v["name"] for v in _done(get("/canary/status", spec_ids=["ok"]))] == ["ok"]
    assert get("/canary/status", spec_ids=["nope"]).status_code == 404
    assert get("/canary/status", spec_ids=[]).status_code == 400  # omit it for every job


def test_unknown_sessions_are_404(get):
    for path, body in (
        ("/canary/query/session", {"session_id": "nope"}),
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


def test_schema_describes_every_endpoint(get):
    data = _done(get("/canary/schema"))
    assert data["endpoints"]["/canary/run"]["lane"] == "work"
    assert "pathspec" in data["endpoints"]["/canary/run"]["request"]["properties"]
    assert data["endpoints"]["/canary/status"]["lane"] == "read"
    assert set(data) == {"envelope", "result", "endpoints"}
    json.dumps(data)


def test_help_describes_every_registered_endpoint(get):
    from _canary.api.dispatch import build_registry

    data = _done(get("/canary/help"))
    assert set(data["endpoints"]) == {e.path for e in build_registry()}
    run = data["endpoints"]["/canary/run"]
    assert run["lane"] == "work" and run["summary"].startswith("Run tests")
    assert run["fields"]["pathspec"].startswith("list[str], default [] -- ")
    job = data["endpoints"]["/canary/query/job"]
    assert job["fields"]["job_id"].startswith("str, required -- ")
    assert data["endpoints"]["/canary/hpc/run"]["lane"] == "work"  # a plugin's endpoint
    assert data["endpoints"]["/canary/query/sessions"]["fields"] == {}
