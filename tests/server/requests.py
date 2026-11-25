# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Server behaviour through the file protocol: recovery, environment, paths, the rm guard.

Ordering, exit codes and cancellation are in inbox.py.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

from _canary.api import requests
from _canary.api.dispatch import accept
from _canary.service.fs import server
from _canary.service.fs.testing import drop
from _canary.service.fs.testing import read_json
from _canary.service.fs.testing import request_dir
from _canary.service.fs.testing import run
from _canary.service.fs.testing import start_server_process
from _canary.service.fs.testing import status
from _canary.service.fs.testing import wait_for
from _canary.service.fs.testing import wait_result
from _canary.workspace.workspace import Workspace


def _canary(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "canary", *args], cwd=cwd, capture_output=True, text=True
    )


def _stdout(root, request_id):
    return (request_dir(root, request_id) / "stdout").read_text()


def test_restart_fails_a_request_left_running_and_requeues_the_rest(root):
    for request_id in ("left-running", "left-claimed"):
        accept(request_id, run(["ok"]), user="u", workspace_root=root)
    requests.work_queue(root).claim(limit=2)  # a dead server had claimed both, and started one
    requests.write_status(request_dir(root, "left-running"), state="running")

    srv = server.Server(root)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    try:
        assert wait_result(root, "left-claimed")["data"]["exit_code"] == 0
    finally:
        srv.request_stop()
        thread.join(30)
    result = read_json(request_dir(root, "left-running") / "result.json")
    assert (result["state"], result["status_code"]) == ("failed", 500)
    assert "exited" in result["error"]


@pytest.mark.skipif(os.getenv("CI") is not None, reason="Skipping in CI")
def test_removing_the_workspace_kills_the_running_request(root):
    srv = server.Server(root)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    drop(root, "slow", run(["slow"]))
    wait_for(lambda: status(root, "slow").get("state") == "running")
    running = srv._running  # the pid is the server's own business (not in status.json)
    assert running is not None
    pid = running.proc.pid
    root.rename(root.parent / "moved")
    wait_for(lambda: not _pid_alive(pid), 15)
    assert not root.exists()  # nothing was recreated
    thread.join(15)


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


ENV_PROBE = (
    "import os, sys\ndef test():\n"
    '    print("SERVER_SIDE=" + os.environ.get("SERVER_SIDE", "-"))\n'
    '    print("CALLER_SIDE=" + os.environ.get("CALLER_SIDE", "-"))\n'
    '    print("EXPLICIT=" + os.environ.get("EXPLICIT", "-"))\n'
    '    print("PWD=" + os.environ.get("PWD", "-"))\n'
    '    print("SNAPSHOT=" + os.environ.get("CANARY_SERVER_CONFIG", "-"))\n'
    '    return 0\nif __name__ == "__main__":\n    sys.exit(test())\n'
)


def test_requests_run_in_the_servers_environment(root, monkeypatch):
    """The server's environment at start applies, plus only the request's explicit env."""
    workspace = root.parent
    (workspace / "probe").mkdir()
    (workspace / "probe" / "probe.pyt").write_text(ENV_PROBE)
    monkeypatch.setenv("SERVER_SIDE", "loaded")  # e.g. `module load` before `server start`
    srv = start_server_process(workspace)  # inherits pytest's $PWD, not the workspace
    monkeypatch.delenv("SERVER_SIDE")
    monkeypatch.setenv("CALLER_SIDE", "desktop")  # the caller's own environment
    try:
        drop(root, "plain", run(["probe"], only="all"))
        explicit = {**run(["probe"], only="all"), "env": {"EXPLICIT": "yes"}}
        time.sleep(0.02)
        drop(root, "explicit", explicit)
        for request_id in ("plain", "explicit"):
            assert wait_result(root, request_id)["data"]["exit_code"] == 0
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    srv.wait(30)
    texts = sorted(p.read_text() for p in root.glob("sessions/*/probe/canary-out.txt"))
    assert len(texts) == 2
    assert all("SERVER_SIDE=loaded" in text for text in texts)
    assert all("CALLER_SIDE=-" in text for text in texts)
    assert sum("EXPLICIT=yes" in text for text in texts) == 1
    assert all(f"PWD={workspace}\n" in text for text in texts)  # the request's cwd
    assert all("SNAPSHOT=-" in text for text in texts)  # the server's start-up stays its own


def test_reruns_and_ids_target_the_servers_workspace_from_any_cwd(root, serving):
    """`run --only=failed` and `run JOBID` act on the server's workspace, whatever the cwd."""
    drop(root, "first", run(["failing"]))
    assert wait_result(root, "first")["data"]["exit_code"] != 0
    results = Workspace.load(root).db.get_results()
    failing_id = next(r["id"] for r in results.values() if r["spec_name"] == "failing")

    drop(root, "rerun", {**run([], only="failed"), "cwd": "ok"})
    wait_result(root, "rerun")
    assert "1 failed" in _stdout(root, "rerun"), _stdout(root, "rerun")
    drop(root, "by-id", {**run([failing_id[:7]]), "cwd": "ok"})
    wait_result(root, "by-id")
    by_id = _stdout(root, "by-id") + (request_dir(root, "by-id") / "stderr").read_text()
    assert f"Running spec {failing_id[:7]}" in by_id
    assert not (root.parent / "ok" / ".canary").exists()  # no stray workspace in the cwd


def test_relative_cwd_runs_under_the_servers_anchor(root, serving):
    drop(root, "here", {**run(["."], only="all"), "cwd": "ok"})
    result = wait_result(root, "here")
    assert result["data"]["exit_code"] == 0 and result["cwd"] == "ok"
    assert "1 pass" in _stdout(root, "here")


def test_rm_and_wipe_are_refused_while_a_server_runs(root, serving):
    workspace = root.parent
    for args in (("rm",), ("run", "-w", "ok")):
        proc = _canary(workspace, *args)
        assert proc.returncode != 0 and "canary server stop" in proc.stderr, args
    assert (root / "WORKSPACE.TAG").exists()


def test_rm_works_once_the_server_stops(root, serving):
    serving.stop()
    assert _canary(root.parent, "rm").returncode == 0
    assert not root.exists()


def test_a_request_body_cannot_wipe_the_workspace(root, serving):
    drop(root, "wipe", run(["ok"], wipe_workspace=True))
    assert wait_result(root, "wipe")["status_code"] == 400
    assert (root / "WORKSPACE.TAG").exists()
