# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Server lifecycle: the lock, heartbeat, stop sentinel and stale-server recovery."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from canary_server import server


def _wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _info(root) -> server.ServerInfo:
    info = server.read_info(root)
    assert info is not None
    return info


def _tag(root):
    """Make *root* look like a workspace root (the server stops when its tag is gone)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "WORKSPACE.TAG").write_text("")
    return root


@pytest.fixture
def running(tmp_path, monkeypatch):
    """A server running in a thread for workspace root *tmp_path*."""
    monkeypatch.setattr(server, "HEARTBEAT_INTERVAL", 0.05)
    _tag(tmp_path)
    srv = server.Server(tmp_path)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    assert _wait_for(lambda: server.read_info(tmp_path) is not None)
    yield srv, thread
    srv.request_stop()
    thread.join(5)


def test_running_server_publishes_a_live_heartbeat(tmp_path, running):
    info = server.read_info(tmp_path)
    assert info is not None and info.pid == os.getpid() and info.is_alive()
    first = info.heartbeat
    assert _wait_for(lambda: _info(tmp_path).heartbeat > first)


def test_a_second_server_is_refused(tmp_path, running):
    with pytest.raises(server.ServerRunningError, match="already running"):
        server.Server(tmp_path).run()


def test_stop_sentinel_stops_the_server_and_removes_its_files(tmp_path, running):
    _, thread = running
    assert server.stop(tmp_path, timeout=5) is True
    thread.join(5)
    assert not thread.is_alive()
    left = {p.name for p in server.server_dir(tmp_path).iterdir()}
    assert not left & {"server.json", "server.lock", "stop"}


def test_stop_without_a_server_reports_false(tmp_path):
    assert server.stop(tmp_path) is False


def test_a_dead_servers_lock_is_taken_over(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "HEARTBEAT_INTERVAL", 0.05)
    _tag(tmp_path)
    directory = server.server_dir(tmp_path)
    directory.mkdir(parents=True)
    (directory / "server.lock").write_text("1@elsewhere\n")
    stale = {"pid": 1, "host": "elsewhere", "started": 0.0, "heartbeat": 0.0, "version": "0"}
    (directory / "server.json").write_text(json.dumps(stale))
    assert not _info(tmp_path).is_alive()

    srv = server.Server(tmp_path)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    assert _wait_for(lambda: getattr(server.read_info(tmp_path), "pid", None) == os.getpid())
    srv.request_stop()
    thread.join(5)


def test_server_exits_when_its_workspace_disappears(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "HEARTBEAT_INTERVAL", 0.05)
    monkeypatch.setattr(server, "TICK", 0.05)
    root = _tag(tmp_path / "ws")
    thread = threading.Thread(target=server.Server(root).run, daemon=True)
    thread.start()
    assert _wait_for(lambda: server.read_info(root) is not None)
    root.rename(tmp_path / "moved")  # what canary rm / run -w do first
    thread.join(10)
    assert not thread.is_alive()
    assert not root.exists()  # nothing was recreated


def test_same_host_dead_pid_is_not_alive():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    info = server.ServerInfo(proc.pid, server.socket.gethostname(), 0.0, time.time(), "0")
    assert not info.is_alive()


def test_cli_start_blocks_until_stop(tmp_path):
    def canary(*args):
        return subprocess.run(
            [sys.executable, "-m", "canary", *args], cwd=tmp_path, capture_output=True, text=True
        )

    assert canary("init", ".").returncode == 0
    proc = start_server_process(tmp_path)
    try:
        status = canary("server", "status", "--json")
        assert status.returncode == 0 and json.loads(status.stdout)["alive"] is True
        second = canary("server", "start")
        assert second.returncode != 0 and "already running" in second.stderr + second.stdout
    finally:
        assert canary("server", "stop").returncode == 0
    assert proc.wait(15) == 0
    status = canary("server", "status", "--json")
    assert status.returncode == 1 and json.loads(status.stdout)["alive"] is False


def test_sighup_stops_the_server_cleanly(tmp_path):
    subprocess.run([sys.executable, "-m", "canary", "init", "."], cwd=tmp_path, check=True)
    proc = start_server_process(tmp_path)
    proc.send_signal(signal.SIGHUP)
    assert proc.wait(15) == 0
    assert not (server.server_dir(tmp_path / ".canary") / "server.lock").exists()


def start_server_process(cwd, timeout=15.0):
    """``canary server start &``: start the blocking server in the background and wait for it."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "canary", "server", "start"],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    root = Path(cwd) / ".canary"
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = server.read_info(root)
        if info is not None and info.pid == proc.pid and info.is_alive():
            return proc
        assert proc.poll() is None, "server exited during startup"
        time.sleep(0.05)
    proc.kill()
    raise AssertionError("server did not start")
