# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Requests end to end: submit, FIFO execution, exit codes, cancel, recovery, --connect."""

import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

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


def _request_id(text):
    match = re.search(r"request (\S+) queued", text)
    assert match is not None, text
    return match.group(1)


def _connect(cwd, *args):
    """``canary --connect=WHERE COMMAND ARGS`` (returns at once), then ``server wait``."""
    queued = _canary(cwd, *args)
    assert queued.returncode == 0, queued.stderr
    request_id = _request_id(queued.stdout)
    return _canary(
        cwd, *[a for a in args if a.startswith("--connect")], "server", "wait", request_id
    )


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
    assert split(["--connect=.", "run", "-k", "fast", "tests"], "run") == (
        [],
        ["-k", "fast", "tests"],
    )
    assert split(["-C", "/x", "-p", "mod", "--connect", "/w", "run", "t"], "run") == (
        ["-p", "mod"],
        ["t"],
    )
    assert split(["-C/x", "--connect=file:///w", "exec", "abc"], "exec") == ([], ["abc"])
    with pytest.raises(ValueError):
        split(["--connect=.", "info"], "run")


def test_make_request_rejects_commands_the_server_does_not_run():
    with pytest.raises(ValueError, match="runs locally"):
        requests.make_request("status", [])


def test_server_runs_these_commands():
    runs = requests.server_runs
    for command in ("run", "exec", "collect", "select"):
        assert runs(command, ["x"])
    assert runs("hpc", ["run", "tests"])
    assert not runs("hpc", ["exec", "batch"]) and not runs("hpc", [])
    assert not runs("status", [])
    with pytest.raises(ValueError, match="'hpc exec' runs locally"):
        requests.make_request("hpc", ["exec", "batch"])


def test_make_request_carries_no_client_environment_unless_given(monkeypatch):
    monkeypatch.setenv("CANARY_FOO", "1")
    monkeypatch.setenv("PATH", "/client/only")
    assert requests.make_request("run", ["t"])["env"] == {}
    assert requests.make_request("run", ["t"], env={"MY_FLAG": "1"})["env"] == {"MY_FLAG": "1"}
    with pytest.raises(ValueError, match="string values"):
        requests.make_request("run", ["t"], env={"N": 1})  # ty: ignore[invalid-argument-type]


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
        proc = _connect(workspace, "--connect=.", "run", "ok")
        assert proc.returncode == 0, proc.stderr
        assert "1 pass" in proc.stdout
        assert _connect(workspace, "--connect=.", "run", "failing").returncode != 0
        assert "without --connect" in _canary(workspace, "--connect=.", "info").stderr
        assert "canary hpc help' without" in _canary(workspace, "--connect=.", "hpc", "help").stderr

        assert _connect(workspace, "--connect=.", "collect", "ok").returncode == 0
        assert _connect(workspace, "--connect=.", "select", "-k", "ok", "picked").returncode == 0
        tag = _canary(workspace, "info", "--tag", "picked")
        assert tag.returncode == 0 and "picked" in tag.stdout

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


def test_removing_the_workspace_kills_the_running_request(serving, workspace):
    request_id = _submit(serving, workspace, "slow")
    _wait_until_running(serving, request_id)
    pid = requests.get(serving, request_id)["pid"]
    serving.rename(workspace / "moved")
    deadline = time.time() + 15
    while time.time() < deadline and _pid_alive(pid):
        time.sleep(0.05)
    assert not _pid_alive(pid)
    assert not serving.exists()


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_rm_and_wipe_are_refused_while_a_server_runs(serving, workspace):
    for args in (("rm",), ("run", "-w", "ok")):
        proc = _canary(workspace, *args)
        assert proc.returncode != 0 and "canary server stop" in proc.stderr, args
    proc = _canary(workspace, "--connect=.", "run", "-w", "ok")
    assert proc.returncode != 0 and "cannot go through the server" in proc.stderr
    assert (serving / "WORKSPACE.TAG").exists()


def test_rm_works_once_the_server_stops(workspace, monkeypatch):
    root = workspace / ".canary"
    monkeypatch.setattr(server, "TICK", 0.05)
    srv = server.Server(root)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while server.read_info(root) is None and time.time() < deadline:
        time.sleep(0.05)
    srv.request_stop()
    thread.join(10)
    assert _canary(workspace, "rm").returncode == 0
    assert not root.exists()


def test_cli_refuses_requests_without_a_server(workspace):
    proc = _canary(workspace, "--connect=.", "run", "ok")
    assert proc.returncode != 0 and "canary server start" in proc.stderr


def test_connect_finds_the_workspace_from_where_and_keeps_the_callers_directory(
    workspace, tmp_path_factory
):
    """WHERE starts the upward workspace search; relative paths stay relative to the caller."""
    srv = start_server_process(workspace)
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (elsewhere / "mine").mkdir()
    (elsewhere / "mine" / "mine.pyt").write_text(PASSING)
    try:
        # from a subdirectory of the workspace tree
        proc = _connect(workspace / "ok", "--connect=.", "run", "--only", "all", ".")
        assert proc.returncode == 0 and "1 pass" in proc.stdout, proc.stderr
        # from outside it: `mine` resolves in the caller's directory, not the workspace's
        for where in (str(workspace / "ok"), f"file://{workspace}"):
            proc = _connect(elsewhere, f"--connect={where}", "run", "--only", "all", "mine")
            assert proc.returncode == 0 and "1 pass" in proc.stdout, proc.stderr
        status = _canary(elsewhere, f"--connect={workspace}", "server", "status", "--json")
        assert status.returncode == 0 and json.loads(status.stdout)["alive"] is True
        bad = _canary(elsewhere, "--connect=ssh://host/ws", "run", "mine")
        assert bad.returncode != 0 and "only file://" in bad.stderr
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    assert srv.wait(30) == 0


def test_connect_returns_at_once_and_the_server_terminal_shows_the_output(workspace):
    srv = start_server_process(workspace, stdout=subprocess.PIPE)
    try:
        queued = _canary(workspace, "--connect=.", "run", "--only", "all", "ok")
        assert queued.returncode == 0 and "canary server wait" in queued.stdout
        assert "1 pass" not in queued.stdout  # the client does not stream
        assert "version:" not in queued.stdout + queued.stderr  # no banner on the client
        request_id = _request_id(queued.stdout)
        assert _canary(workspace, "server", "wait", request_id, "--quiet").returncode == 0
        saved = (requests.request_dir(workspace / ".canary", request_id) / "stdout").read_text()
        assert "1 pass" in saved
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    terminal = srv.communicate(timeout=30)[0].decode()
    assert request_id in terminal and "1 pass" in terminal
    # one banner: the server's own (server start greets its terminal); the child prints none
    assert terminal.count("version:") == 1


ENV_PROBE = (
    "import os, sys\ndef test():\n"
    '    print("SERVER_SIDE=" + os.environ.get("SERVER_SIDE", "-"))\n'
    '    print("CLIENT_SIDE=" + os.environ.get("CLIENT_SIDE", "-"))\n'
    '    print("EXPLICIT=" + os.environ.get("EXPLICIT", "-"))\n'
    '    print("PWD=" + os.environ.get("PWD", "-"))\n'
    '    return 0\nif __name__ == "__main__":\n    sys.exit(test())\n'
)


def test_requests_run_in_the_servers_environment(workspace, monkeypatch):
    """The server's environment at start applies; client variables only via explicit env."""
    (workspace / "probe").mkdir()
    (workspace / "probe" / "probe.pyt").write_text(ENV_PROBE)
    monkeypatch.setenv("SERVER_SIDE", "loaded")  # e.g. `module load` before `server start`
    srv = start_server_process(workspace)  # inherits pytest's $PWD, not the workspace
    monkeypatch.delenv("SERVER_SIDE")
    try:
        env = {**os.environ, "CLIENT_SIDE": "desktop"}
        queued = subprocess.run(
            [sys.executable, "-m", "canary", "--connect=.", "run", "--only", "all", "probe"],
            cwd=workspace,
            capture_output=True,
            text=True,
            env=env,
        )
        first = _request_id(queued.stdout)
        posted = _canary(
            workspace,
            "server",
            "post",
            json.dumps(
                {"command": "run", "args": ["--only", "all", "probe"], "env": {"EXPLICIT": "yes"}}
            ),
        )
        second = json.loads(posted.stdout)["id"]
        for request_id in (first, second):
            assert _canary(workspace, "server", "wait", request_id, "--quiet").returncode == 0
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    srv.wait(30)
    root = workspace / ".canary"
    texts = sorted(p.read_text() for p in root.glob("sessions/*/probe/canary-out.txt"))
    assert len(texts) == 2
    assert all("SERVER_SIDE=loaded" in text for text in texts)
    assert all("CLIENT_SIDE=-" in text for text in texts)
    assert sum("EXPLICIT=yes" in text for text in texts) == 1
    assert all(f"PWD={workspace}\n" in text for text in texts)  # the request's cwd


def test_post_reads_the_request_from_a_file_or_stdin(workspace):
    request = json.dumps({"command": "run", "args": ["--only", "all", "ok"]})
    (workspace / "request.json").write_text(request)
    srv = start_server_process(workspace)
    try:
        from_file = _canary(workspace, "server", "post", "request.json")
        from_stdin = subprocess.run(
            [sys.executable, "-m", "canary", "server", "post", "-"],
            cwd=workspace,
            input=request,
            capture_output=True,
            text=True,
        )
        for proc in (from_file, from_stdin):
            request_id = json.loads(proc.stdout)["id"]
            assert _canary(workspace, "server", "wait", request_id, "--quiet").returncode == 0
        missing = _canary(workspace, "server", "post", "nope.json")
        assert missing.returncode != 0 and "cannot read nope.json" in missing.stderr
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    assert srv.wait(30) == 0


def test_reruns_and_paths_target_the_servers_workspace_from_anywhere(workspace, tmp_path_factory):
    """`run --only=failed` and `run JOBID` act on the server's workspace; paths stay the caller's."""
    srv = start_server_process(workspace)
    outside = tmp_path_factory.mktemp("outside")
    (outside / "mine").mkdir()
    (outside / "mine" / "mine.pyt").write_text(PASSING)
    ws = f"--connect={workspace}"
    try:
        assert _connect(workspace, "--connect=.", "run", "failing").returncode != 0
        failing_id = next(
            r["id"] for r in _results(workspace).values() if r["spec_name"] == "failing"
        )

        inside = _connect(workspace / "ok", "--connect=.", "run", "--only=failed")
        assert "1 failed" in inside.stdout, inside.stdout
        rerun = _connect(outside, ws, "run", "--only=failed")
        assert "1 failed" in rerun.stdout, rerun.stdout
        by_id = _connect(outside, ws, "run", failing_id[:7])
        assert f"Running spec {failing_id[:7]}" in by_id.stdout + by_id.stderr
        scanned = _connect(outside, ws, "run", "mine")
        assert scanned.returncode == 0 and "1 pass" in scanned.stdout, scanned.stdout
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    srv.wait(30)
    assert not (outside / ".canary").exists()  # no stray workspace where the client was
    assert "mine" in {r["spec_name"] for r in _results(workspace).values()}


def _results(workspace):
    from _canary.workspace.workspace import Workspace

    return Workspace.load(workspace).db.get_results()


def test_cwd_is_recorded_relative_to_the_anchor_and_resolved_on_the_server():
    """A share mounted at /projects here and /gpfs/.../dev there still maps."""
    assert requests.relative_cwd("/client/view/ws", "/client/view/ws") == "."
    assert requests.relative_cwd("/client/view/ws/examples", "/client/view/ws") == "examples"
    server_root = Path("/gpfs/tjfulle/Workspace/Projects/Canary/dev/src/canary/.canary")
    assert requests.resolve_cwd("examples", server_root) == str(server_root.parent / "examples")
    assert requests.resolve_cwd(".", server_root) == str(server_root.parent)
    assert requests.resolve_cwd("/abs/dir", server_root) == "/abs/dir"
    assert requests.make_request("run", ["t"])["cwd"] == "."


def test_relative_cwd_runs_under_the_servers_anchor(workspace):
    srv = start_server_process(workspace)
    try:
        queued = _canary(workspace / "ok", "--connect=.", "run", "--only", "all", ".")
        connect_id = _request_id(queued.stdout)
        assert (
            requests.read_request(requests.request_dir(workspace / ".canary", connect_id))["cwd"]
            == "ok"
        )
        posted = _canary(
            workspace,
            "server",
            "post",
            json.dumps({"command": "run", "args": ["--only", "all", "."], "cwd": "ok"}),
        )
        post_id = json.loads(posted.stdout)["id"]
        for request_id in (connect_id, post_id):
            waited = _canary(workspace, "server", "wait", request_id)
            assert waited.returncode == 0 and "1 pass" in waited.stdout, waited.stdout
            record = requests.get(workspace / ".canary", request_id)
            assert record["cwd"] == str(workspace / "ok")  # resolved by the server
    finally:
        assert _canary(workspace, "server", "stop").returncode == 0
    assert srv.wait(30) == 0


def test_relative_cwd_keeps_symlinks_inside_the_tree(tmp_path):
    (tmp_path / "ws" / "docs" / "examples").mkdir(parents=True)
    (tmp_path / "ws" / "examples").symlink_to(tmp_path / "ws" / "docs" / "examples")
    assert requests.relative_cwd(tmp_path / "ws" / "examples", tmp_path / "ws") == "examples"
    # reached through a link from outside the tree: fall back to the resolved paths
    (tmp_path / "view").symlink_to(tmp_path / "ws")
    assert requests.relative_cwd(tmp_path / "view" / "docs", tmp_path / "ws") == "docs"
