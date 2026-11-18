# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Server lifecycle: the lock, heartbeat, stop sentinel and stale-server recovery."""

import json
import os
import subprocess
import sys
import threading
import time

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


@pytest.fixture
def running(tmp_path, monkeypatch):
    """A server running in a thread for workspace root *tmp_path*."""
    monkeypatch.setattr(server, "HEARTBEAT_INTERVAL", 0.05)
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
    assert sorted(p.name for p in server.server_dir(tmp_path).iterdir()) == []


def test_stop_without_a_server_reports_false(tmp_path):
    assert server.stop(tmp_path) is False


def test_a_dead_servers_lock_is_taken_over(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "HEARTBEAT_INTERVAL", 0.05)
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


def test_same_host_dead_pid_is_not_alive():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    info = server.ServerInfo(proc.pid, server.socket.gethostname(), 0.0, time.time(), "0")
    assert not info.is_alive()


def test_cli_start_status_stop(tmp_path):
    def canary(*args):
        return subprocess.run(
            [sys.executable, "-m", "canary", *args], cwd=tmp_path, capture_output=True, text=True
        )

    assert canary("init", ".").returncode == 0
    try:
        assert canary("server", "start").returncode == 0
        status = canary("server", "status", "--json")
        assert status.returncode == 0 and json.loads(status.stdout)["alive"] is True
        assert (
            "already running" in canary("server", "start").stderr + canary("server", "start").stdout
        )
    finally:
        assert canary("server", "stop").returncode == 0
    status = canary("server", "status", "--json")
    assert status.returncode == 1 and json.loads(status.stdout) == {"alive": False}
