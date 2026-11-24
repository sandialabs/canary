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

import pytest

from _canary.service.fs import server
from _canary.service.fs.testing import start_server_process


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
    info = server.live_server(tmp_path)
    assert info is not None and info.pid == os.getpid()
    first = info.beat
    assert _wait_for(lambda: _info(tmp_path).beat > first)


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
    monkeypatch.setattr(server, "OBSERVE_FOR", 0.5)
    _tag(tmp_path)
    directory = server.server_dir(tmp_path)
    directory.mkdir(parents=True)
    _write_info(tmp_path, heartbeat=0.0)
    assert server.live_server(tmp_path) is None  # another host, beat not advancing

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


def _write_info(root, pid=1, host="elsewhere", **fields):
    """What a server writes: ``pid@host`` in the lock, the public fields in server.json."""
    directory = server.server_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "server.lock").write_text(f"{pid}@{host}\n")
    info = {"version": 1, "started": 0.0, "heartbeat": time.time(), "canary_version": "0"}
    info.update(fields)
    (directory / "server.json").write_text(json.dumps(info))


def test_same_host_dead_pid_is_not_alive(tmp_path):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    _write_info(tmp_path, pid=proc.pid, host=server.socket.gethostname())
    assert server.live_server(tmp_path) is None


def test_another_hosts_server_is_alive_while_it_beats_whatever_the_clocks_say(tmp_path):
    """Regression: liveness compared the reader's clock with another host's heartbeat."""
    _write_info(tmp_path, heartbeat=time.time() - 3600.0, beat=1)  # its clock is an hour behind
    stop = threading.Event()

    def beat():
        n = 1
        while not stop.wait(0.1):
            n += 1
            _write_info(tmp_path, heartbeat=time.time() - 3600.0, beat=n)

    beater = threading.Thread(target=beat, daemon=True)
    beater.start()
    try:
        assert server.live_server(tmp_path, observe=2.0) is not None
    finally:
        stop.set()
        beater.join(5)
    # stopped beating: dead, even with a heartbeat time that looks fresh (clock ahead)
    _write_info(tmp_path, heartbeat=time.time() + 3600.0, beat=7)
    assert server.live_server(tmp_path, observe=0.6) is None


def test_cli_start_blocks_until_stop(tmp_path):
    def canary(*args):
        return subprocess.run(
            [sys.executable, "-m", "canary", *args], cwd=tmp_path, capture_output=True, text=True
        )

    assert canary("init", ".").returncode == 0
    proc = start_server_process(tmp_path)
    root = tmp_path / ".canary"
    try:
        assert server.live_server(root) is not None
        second = canary("server", "start")
        assert second.returncode != 0 and "already running" in second.stderr + second.stdout
    finally:
        assert canary("server", "stop").returncode == 0
    assert proc.wait(15) == 0
    assert server.live_server(root) is None
    assert not (server.server_dir(root) / "server.json").exists()


def test_sighup_stops_the_server_cleanly(tmp_path):
    subprocess.run([sys.executable, "-m", "canary", "init", "."], cwd=tmp_path, check=True)
    proc = start_server_process(tmp_path)
    proc.send_signal(signal.SIGHUP)
    assert proc.wait(15) == 0
    assert not (server.server_dir(tmp_path / ".canary") / "server.lock").exists()


def test_start_creates_a_workspace_and_w_recreates_it(tmp_path):
    def canary(*args, cwd=tmp_path):
        return subprocess.run(
            [sys.executable, "-m", "canary", *args], cwd=cwd, capture_output=True, text=True
        )

    proc = start_server_process(tmp_path)  # no workspace yet: one is created here
    (tmp_path / ".canary" / "marker").touch()
    try:
        refused = canary("server", "start", "-w")  # never wipes a live server's workspace
        assert refused.returncode != 0 and "stop it first" in refused.stderr + refused.stdout
        assert (tmp_path / ".canary" / "marker").exists()
    finally:
        assert canary("server", "stop").returncode == 0
    assert proc.wait(15) == 0

    proc = start_server_process(tmp_path, args=["-w"])  # fresh workspace
    try:
        assert not (tmp_path / ".canary" / "marker").exists()
        (tmp_path / "sub").mkdir()
        inner = canary("server", "start", "-w", cwd=tmp_path / "sub")
        assert inner.returncode != 0 and "will not be wiped" in inner.stderr + inner.stdout
    finally:
        assert canary("server", "stop").returncode == 0
    assert proc.wait(15) == 0


def test_start_installs_agent_bootstrap_files_beside_the_workspace(tmp_path):
    def canary(*args, cwd=tmp_path):
        return subprocess.run(
            [sys.executable, "-m", "canary", *args], cwd=cwd, capture_output=True, text=True
        )

    assert canary("init", ".").returncode == 0
    (tmp_path / "CLAUDE.md").write_text("# My project\n")
    stale = tmp_path / ".opencode" / "skills" / "canary-server" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("not canary's\n")  # a conflict: --force is implied
    proc = start_server_process(tmp_path, args=["--claude", "--skills", "opencode"])
    try:
        claude_md = (tmp_path / "CLAUDE.md").read_text()
        assert claude_md.startswith("# My project\n")  # refreshed, not replaced
        assert "<!-- BEGIN CANARY GUIDANCE -->" in claude_md
        assert (tmp_path / ".claude" / "skills" / "canary-server" / "SKILL.md").is_file()
        assert "name: canary-server" in stale.read_text()
        assert (tmp_path / ".agent" / "canary" / "BOOTSTRAP.md").is_file()
    finally:
        assert canary("server", "stop").returncode == 0
    assert proc.wait(15) == 0
