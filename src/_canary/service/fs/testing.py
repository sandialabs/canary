# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Testing utilities for the request server's tests.

The caller side (:func:`drop`, :func:`wait_result`, :func:`cancel`, ...) uses nothing but
files and the standard library, as a real caller would; :class:`Serving` and
:func:`start_server_process` run a server for a test.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import server


def server_dir(root) -> Path:
    return Path(root) / "var" / "server"


def drop(root, request_id: str, envelope, *, name: str | None = None) -> Path:
    """Write ``inbox/<id>.json.tmp``, then rename it to ``inbox/<id>.json``."""
    inbox = server_dir(root) / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    final = inbox / (name or f"{request_id}.json")
    tmp = final.with_name(final.name + ".tmp")
    tmp.write_text(envelope if isinstance(envelope, str) else json.dumps(envelope))
    os.rename(tmp, final)
    return final


def request_dir(root, request_id: str) -> Path:
    return server_dir(root) / "requests" / request_id


def wait_for(predicate, timeout: float = 60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out after {timeout} s")


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def status(root, request_id: str) -> dict:
    return read_json(request_dir(root, request_id) / "status.json") or {}


def wait_result(root, request_id: str, timeout: float = 120.0) -> dict:
    """Poll ``requests/<id>/result.json`` until it exists."""
    return wait_for(lambda: read_json(request_dir(root, request_id) / "result.json"), timeout)


def cancel(root, request_id: str) -> None:
    (request_dir(root, request_id) / "cancel").touch()


def run(pathspec, **body) -> dict:
    return {"path": "/canary/run", "request": {"pathspec": list(pathspec), **body}}


class Serving:
    """A server in a thread; :meth:`stop` and :meth:`start` it again."""

    def __init__(self, root):
        self.root = root
        self.srv: server.Server | None = None
        self.thread: threading.Thread | None = None

    def start(self):
        self.srv = server.Server(self.root)
        self.thread = threading.Thread(target=self.srv.run, daemon=True)
        self.thread.start()
        wait_for(lambda: (server_dir(self.root) / "server.json").exists(), 10)
        wait_for(lambda: (self.root / "share" / "carl").exists(), 10)  # installed just after
        return self

    def stop(self):
        if self.srv is not None and self.thread is not None:
            self.srv.request_stop()
            self.thread.join(60)
            self.srv = self.thread = None


def start_server_process(cwd, timeout=15.0, *, stdout=None, args=(), options=()):
    """``canary [options] server start [args] &``: start the server and wait for it."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "canary", *options, "server", "start", *args],
        cwd=cwd,
        stdout=stdout if stdout is not None else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if stdout is not None else subprocess.DEVNULL,
    )
    root = Path(cwd) / ".canary"
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = server.live_server(root)
        if info is not None and info.pid == proc.pid:
            return proc
        assert proc.poll() is None, "server exited during startup"
        time.sleep(0.05)
    proc.kill()
    raise AssertionError("server did not start")
