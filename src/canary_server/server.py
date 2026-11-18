# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""A workspace's command server: lifecycle (start, stop, status) and its files.

The server's files live in ``<workspace root>/var/server/``:

* ``server.lock`` -- created exclusively by the running server; held for its lifetime.
* ``server.json`` -- pid, host, start time, heartbeat and version, rewritten every
  ``HEARTBEAT_INTERVAL`` seconds.  A server whose heartbeat is older than
  ``STALE_AFTER`` seconds (or whose pid is gone, on the same host) is dead.
* ``stop`` -- sentinel: any process that sees the workspace asks the server to stop.
* ``server.log`` -- output of a server started in the background.

Everything is a file on the workspace's filesystem, so a client on another machine
sees the same state.
"""

import dataclasses
import json
import os
import signal
import socket
import subprocess  # nosec B404
import sys
import threading
import time
from pathlib import Path
from typing import Any

from _canary import version
from _canary.util import logging
from _canary.util.filesystem import atomic_write

logger = logging.get_logger(__name__)

HEARTBEAT_INTERVAL = 2.0
STALE_AFTER = 5 * HEARTBEAT_INTERVAL


class ServerRunningError(Exception):
    """Raised when a live server already owns the workspace."""


def server_dir(workspace_root: Path) -> Path:
    """Return the directory holding a workspace's server files."""
    return Path(workspace_root) / "var" / "server"


@dataclasses.dataclass
class ServerInfo:
    """Contents of ``server.json``."""

    pid: int
    host: str
    started: float
    heartbeat: float
    version: str

    def is_alive(self, *, now: float | None = None) -> bool:
        """True if the heartbeat is fresh and, on this host, the process exists."""
        now = time.time() if now is None else now
        if now - self.heartbeat > STALE_AFTER:
            return False
        if self.host == socket.gethostname():
            return _pid_exists(self.pid)
        return True

    def to_dict(self, *, now: float | None = None) -> dict[str, Any]:
        return {**dataclasses.asdict(self), "alive": self.is_alive(now=now)}


def read_info(workspace_root: Path) -> ServerInfo | None:
    """Return the server's ``server.json``, or ``None`` if there is none (or it is unreadable)."""
    file = server_dir(workspace_root) / "server.json"
    try:
        data = json.loads(file.read_text())
        return ServerInfo(**{f.name: data[f.name] for f in dataclasses.fields(ServerInfo)})
    except (OSError, ValueError, KeyError, TypeError):
        return None


class Server:
    """The server process for one workspace.

    :meth:`run` owns the workspace's server files until it returns: it takes the
    lock, writes the heartbeat, and stops on SIGTERM/SIGINT, on the ``stop`` sentinel,
    or on :meth:`request_stop`.
    """

    def __init__(self, workspace_root: Path) -> None:
        self.dir = server_dir(workspace_root)
        self.lock = self.dir / "server.lock"
        self.info_file = self.dir / "server.json"
        self.stop_file = self.dir / "stop"
        self._stop = threading.Event()
        self.info: ServerInfo | None = None

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Serve until asked to stop."""
        self._acquire()
        previous = self._install_signal_handlers()
        try:
            logger.info(
                f"[bold]Canary server[/] running for {self.dir.parent.parent} (pid {os.getpid()})"
            )
            while not self._stop.is_set():
                self._heartbeat()
                if self.stop_file.exists():
                    break
                self._stop.wait(HEARTBEAT_INTERVAL)
        finally:
            self._release()
            self._restore_signal_handlers(previous)
            logger.info("[bold]Canary server[/] stopped")

    def _acquire(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                info = read_info(self.dir.parent.parent)
                if info is not None and info.is_alive():
                    raise ServerRunningError(
                        f"a server is already running for this workspace (pid {info.pid} on {info.host})"
                    ) from None
                if info is None and time.time() - _mtime(self.lock) < STALE_AFTER:
                    raise ServerRunningError("a server is starting for this workspace") from None
                logger.debug("Removing stale server lock %s", self.lock)
                self.lock.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w") as fh:
                fh.write(f"{os.getpid()}@{socket.gethostname()}\n")
            break
        else:
            raise ServerRunningError(f"could not take the server lock {self.lock}")
        self.stop_file.unlink(missing_ok=True)
        now = time.time()
        self.info = ServerInfo(os.getpid(), socket.gethostname(), now, now, version.__version__)

    def _heartbeat(self) -> None:
        assert self.info is not None
        self.info.heartbeat = time.time()
        atomic_write(self.info_file, json.dumps(dataclasses.asdict(self.info), indent=2))

    def _release(self) -> None:
        for path in (self.info_file, self.stop_file, self.lock):
            path.unlink(missing_ok=True)

    def _install_signal_handlers(self) -> dict[int, Any]:
        if threading.current_thread() is not threading.main_thread():
            return {}
        handler = lambda signum, frame: self.request_stop()
        return {sig: signal.signal(sig, handler) for sig in (signal.SIGTERM, signal.SIGINT)}

    @staticmethod
    def _restore_signal_handlers(previous: dict[int, Any]) -> None:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def start_in_background(workspace_root: Path, *, timeout: float = 15.0) -> ServerInfo:
    """Start a detached server for the workspace and wait until it is up."""
    info = read_info(workspace_root)
    if info is not None and info.is_alive():
        raise ServerRunningError(
            f"a server is already running for this workspace (pid {info.pid} on {info.host})"
        )
    directory = server_dir(workspace_root)
    directory.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "canary", "--canary-dir", str(workspace_root)]
    cmd += ["server", "start", "--foreground"]
    with open(directory / "server.log", "a") as log:
        proc = subprocess.Popen(  # nosec B603
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = read_info(workspace_root)
        if info is not None and info.pid == proc.pid and info.is_alive():
            return info
        if proc.poll() is not None:
            raise RuntimeError(
                f"server exited with code {proc.returncode}; see {directory / 'server.log'}"
            )
        time.sleep(0.1)
    raise RuntimeError(f"server did not start within {timeout} s; see {directory / 'server.log'}")


def stop(workspace_root: Path, *, timeout: float = 15.0) -> bool:
    """Ask the workspace's server to stop and wait for it; return False if none was running."""
    info = read_info(workspace_root)
    directory = server_dir(workspace_root)
    if info is None or not info.is_alive():
        if (directory / "server.lock").exists() and info is not None:
            for name in ("server.json", "server.lock", "stop"):
                (directory / name).unlink(missing_ok=True)
        return False
    (directory / "stop").touch()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not (directory / "server.lock").exists():
            return True
        time.sleep(0.1)
    raise RuntimeError(f"server (pid {info.pid} on {info.host}) did not stop within {timeout} s")


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
