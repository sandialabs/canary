# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Requests end to end: submit, FIFO execution, exit codes, cancel, recovery, --server."""

import io
import json
import subprocess
import sys
import threading
import time

import pytest

from canary_server import requests
from canary_server import server
from canary_server.tests.server import start_server_process

PASSING = (
    'import sys\ndef test():\n    return 0\nif __name__ == "__main__":\n    sys.exit(test())\n'
)
FAILING = (
    'import sys\ndef test():\n    return 1\nif __name__ == "__main__":\n    sys.exit(test())\n'
)
SLOW = (
    "import sys, time\ndef test():\n    time.sleep(30)\n    return 0\n"
    'if __name__ == "__main__":\n    sys.exit(test())\n'
)


def _canary(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "canary", *args], cwd=cwd, capture_output=True, text=True
    )


@pytest.fixture
def workspace(tmp_path):
    """A workspace at *tmp_path* with ok/, failing/ and slow/ test directories."""
    for name, body in (("ok", PASSING), ("failing", FAILING), ("slow", SLOW)):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name}.pyt").write_text(body)
    assert _canary(tmp_path, "init", ".").returncode == 0
    return tmp_path


@pytest.fixture
def serving(workspace, monkeypatch):
    """A server running in a thread for *workspace*; yields the workspace root."""
    monkeypatch.setattr(server, "TICK", 0.05)
    monkeypatch.setattr(server, "INTERRUPT_GRACE", 5.0)
    root = workspace / ".canary"
    srv = server.Server(root)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while server.read_info(root) is None and time.time() < deadline:
        time.sleep(0.05)
    yield root
    srv.request_stop()
    thread.join(30)


def _submit(root, workspace, *args):
    return requests.submit(root, requests.make_request("run", list(args), cwd=str(workspace)))


def _wait_until_running(root, request_id, timeout=30.0):
    deadline = time.time() + timeout
    while requests.get(root, request_id)["state"] != "running":
        assert time.time() < deadline, f"{request_id} never started"
        time.sleep(0.05)


def _follow(root, request_id):
    return requests.follow(root, request_id, stdout=io.StringIO(), stderr=io.StringIO(), poll=0.05)


def test_split_command_line():
    split = requests.split_command_line
    assert split(["--server", "run", "-k", "fast", "tests"], "run") == ([], ["-k", "fast", "tests"])
    assert split(["-C", "/x", "-p", "mod", "--server", "run", "t"], "run") == (["-p", "mod"], ["t"])
    assert split(["-C/x", "--server", "exec", "abc"], "exec") == ([], ["abc"])
    with pytest.raises(ValueError):
        split(["--server", "info"], "run")


def test_make_request_rejects_commands_the_server_does_not_run():
    with pytest.raises(ValueError, match="runs locally"):
        requests.make_request("status", [])


def test_make_request_carries_only_the_allowed_environment(monkeypatch):
    monkeypatch.setenv("CANARY_FOO", "1")
    monkeypatch.setenv("CANARY_LEVEL", "3")
    monkeypatch.setenv("SECRET_TOKEN", "x")
    env = requests.make_request("run", ["t"])["env"]
    assert env["CANARY_FOO"] == "1"
    assert "CANARY_LEVEL" not in env and "SECRET_TOKEN" not in env


def test_requests_run_in_order_and_report_their_exit_codes(serving, workspace):
    first = _submit(serving, workspace, "ok")
    second = _submit(serving, workspace, "failing")
    assert _follow(serving, first) == 0
    code = _follow(serving, second)
    a, b = requests.get(serving, first), requests.get(serving, second)
    assert a["state"] == b["state"] == "done"
    assert code == b["returncode"] != 0
    assert a["finished"] <= b["started"]
    assert "1 pass" in (requests.request_dir(serving, first) / "stdout").read_text()


def test_cancel_a_queued_request_never_runs_it(serving, workspace):
    running = _submit(serving, workspace, "slow")
    _wait_until_running(serving, running)
    queued = _submit(serving, workspace, "ok")
    assert requests.get(serving, queued)["position"] == 1
    assert requests.cancel(serving, queued) == "cancelled"
    requests.cancel(serving, running)
    assert _follow(serving, queued) == requests.CANCELLED_RETURNCODE
    assert _follow(serving, running) == requests.CANCELLED_RETURNCODE
    assert not (requests.request_dir(serving, queued) / "stdout").exists()


def test_cancel_a_running_request_interrupts_it(serving, workspace):
    request_id = _submit(serving, workspace, "slow")
    _wait_until_running(serving, request_id)
    assert requests.cancel(serving, request_id) == "running"
    assert _follow(serving, request_id) == requests.CANCELLED_RETURNCODE
    record = requests.get(serving, request_id)
    assert record["state"] == "cancelled" and record["finished"] - record["started"] < 20


def test_restart_fails_a_request_left_running_and_requeues_the_rest(workspace, monkeypatch):
    root = workspace / ".canary"
    left_running = _submit(root, workspace, "ok")
    left_claimed = _submit(root, workspace, "ok")
    queue = requests.inbox(root)
    queue.claim(limit=2)  # a dead server had claimed both, and started the first
    requests.write_status(requests.request_dir(root, left_running), state="running", pid=1)

    monkeypatch.setattr(server, "TICK", 0.05)
    srv = server.Server(root)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    try:
        assert _follow(root, left_claimed) == 0
    finally:
        srv.request_stop()
        thread.join(30)
    record = requests.get(root, left_running)
    assert record["state"] == "failed" and "exited" in record["reason"]


def test_cli_server_flag_and_post(workspace):
    srv = start_server_process(workspace)
    try:
        proc = _canary(workspace, "--server", "run", "ok")
        assert proc.returncode == 0, proc.stderr
        assert "1 pass" in proc.stdout
        assert _canary(workspace, "--server", "run", "failing").returncode != 0
        assert "without --server" in _canary(workspace, "--server", "info").stderr

        posted = _canary(
            workspace,
            "server",
            "post",
            json.dumps({"command": "run", "args": ["--only", "all", "ok"]}),
        )
        request_id = json.loads(posted.stdout)["id"]
        assert _canary(workspace, "server", "wait", request_id, "--quiet").returncode == 0
        assert json.loads(_canary(workspace, "server", "get", request_id).stdout)["state"] == "done"
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    assert srv.wait(30) == 0


def test_cli_refuses_requests_without_a_server(workspace):
    proc = _canary(workspace, "--server", "run", "ok")
    assert proc.returncode != 0 and "canary server start" in proc.stderr
