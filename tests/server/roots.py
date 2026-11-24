# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Requests reach only the workspace and server:allowed_roots; results publish no other path."""

import os
import subprocess
import sys

import pytest

import canary
from _canary.service.fs.testing import Serving
from _canary.service.fs.testing import drop
from _canary.service.fs.testing import run
from _canary.service.fs.testing import wait_result

PASSING = 'import sys\nif __name__ == "__main__":\n    sys.exit(0)\n'


@pytest.fixture
def outside(tmp_path_factory):
    """A test directory outside the workspace."""
    path = tmp_path_factory.mktemp("outside") / "suite"
    path.mkdir()
    (path / "elsewhere.pyt").write_text(PASSING)
    return path


def _serve(root, allowed=None):
    if allowed is not None:
        canary.config.set("server:allowed_roots", allowed)
    return Serving(root).start()


def _forbidden(result):
    assert (result["state"], result["status_code"]) == ("rejected", 403), result
    assert "outside the workspace" in result["error"]


def test_a_run_outside_the_workspace_is_refused(root, outside):
    serving = _serve(root)
    try:
        drop(root, "abs", run([str(outside)]))
        _forbidden(wait_result(root, "abs"))
        os.symlink(outside, root.parent / "link")  # inside by name, outside in fact
        drop(root, "link", run(["link"]))
        _forbidden(wait_result(root, "link"))
        drop(root, "collect", {"path": "/canary/collect", "request": {"roots": [str(outside)]}})
        _forbidden(wait_result(root, "collect"))
        select = {"path": "/canary/select", "request": {"tag": "t", "from_root": [str(outside)]}}
        drop(root, "select", select)
        _forbidden(wait_result(root, "select"))
        hpc = {
            "path": "/canary/hpc/run",
            "request": {"pathspec": [str(outside)], "backend": "local"},
        }
        drop(root, "hpc", hpc)
        _forbidden(wait_result(root, "hpc"))
        drop(root, "inside", run(["ok"]))  # the workspace's own tests still run
        assert wait_result(root, "inside")["data"] == {"exit_code": 0}
    finally:
        serving.stop()


def test_an_allowed_root_may_be_run_and_is_shown_by_name(root, outside):
    serving = _serve(root, {"src": str(outside.parent)})
    try:
        drop(root, "r", run([str(outside)]))
        assert wait_result(root, "r")["data"] == {"exit_code": 0}
        drop(root, "s", {"path": "/canary/status"})
        paths = {
            v["name"]: (v["file_root"], v["file_path"]) for v in wait_result(root, "s")["data"]
        }
        assert paths["elsewhere"] == ("src:suite", "elsewhere.pyt")
        drop(root, "j", {"path": "/canary/query/jobs"})
        jobs = wait_result(root, "j")["data"]
        assert {v["name"]: v["file_root"] for v in jobs}["elsewhere"] == "src:suite"
        assert str(outside) not in str(jobs)
    finally:
        serving.stop()


def test_a_job_from_elsewhere_is_shown_without_its_server_path(root, outside):
    """Collected from the command line, outside every allowed root: only its file name."""
    workspace = root.parent
    done = subprocess.run(
        [sys.executable, "-m", "canary", "run", str(outside)],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    serving = _serve(root)
    try:
        drop(root, "s", {"path": "/canary/status"})
        data = wait_result(root, "s")["data"]
        record = {v["name"]: v for v in data}["elsewhere"]
        assert (record["file_root"], record["file_path"]) == ("…/suite", "elsewhere.pyt")
        assert str(outside) not in str(data)
    finally:
        serving.stop()
