# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""A workspace's command server: lifecycle (start, stop, status) and its files.

The server's files live in ``<workspace root>/var/server/``:

* ``server.lock`` -- created exclusively by the running server and held for its
  lifetime; holds ``pid@host`` (private: callers never need it).
* ``server.json`` -- public: start time, heartbeat time, a ``beat`` counter, the canary
  version and how many requests are running and queued, rewritten every
  ``HEARTBEAT_INTERVAL`` seconds.  See :func:`live_server` for how a reader decides the
  server is alive (without comparing clocks across hosts).
* ``stop`` -- sentinel: any process that sees the workspace asks the server to stop.
* ``config.json`` -- private: the server's configuration snapshot (see :data:`CONFIG_ENV`).
* ``inbox/``, ``rejected/``, ``requests/`` -- the request protocol (:mod:`.inbox`).

At start the server also installs ``<workspace root>/share/carl``, a curl-like client
for that protocol that needs only ``sh`` (:func:`install_carl`).

Everything is a file on the workspace's filesystem, so a caller on another machine
sees the same state.
"""

import contextlib
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
from typing import IO
from typing import Any

from _canary import version
from _canary.api.requests import server_dir
from _canary.util import logging
from _canary.util.filesystem import atomic_write
from _canary.workspace import inuse
from _canary.workspace.locator import workspace_tag

logger = logging.get_logger(__name__)

HEARTBEAT_INTERVAL = 2.0
STALE_AFTER = 5 * HEARTBEAT_INTERVAL
#: How long a reader on another host watches ``beat`` for progress before calling the
#: server dead (a little over two heartbeats).
OBSERVE_FOR = 2.5 * HEARTBEAT_INTERVAL
#: How often the loop looks for work, cancellation and a finished child.
TICK = 0.2
#: Seconds between SIGINT, SIGTERM and SIGKILL when interrupting a request.
INTERRUPT_GRACE = 10.0
#: The variable naming the server's configuration snapshot for a worker.  Canary's start-up
#: (configuration files, ``-p`` plugins, ``-c`` changes, ``canary_configure``) happens once,
#: in ``canary server start``; each worker restores it, as every canary child does.
CONFIG_ENV = "CANARY_SERVER_CONFIG"
#: Default of ``server:retain_days``: finished requests older than this are pruned at start.
RETAIN_DAYS = 7
#: Defaults of ``server:read_workers`` and ``server:read_timeout`` (seconds).
READ_WORKERS = 4
READ_TIMEOUT = 300


class ServerRunningError(Exception):
    """Raised when a live server already owns the workspace."""


@dataclasses.dataclass
class ServerInfo:
    """The server: ``pid``/``host`` from ``server.lock``, the rest from ``server.json``."""

    pid: int
    host: str
    started: float
    heartbeat: float
    version: str
    #: Incremented on every heartbeat; other hosts judge liveness by its progress.
    beat: int = 0

    def to_dict(self, *, alive: bool) -> dict[str, Any]:
        return {**dataclasses.asdict(self), "alive": alive}

    def public(self, *, running: int, queued: int) -> dict[str, Any]:
        """``server.json``: no pid, host or path (callers on other machines read it)."""
        return {
            "version": 1,
            "state": "running",
            "started": self.started,
            "heartbeat": self.heartbeat,
            "beat": self.beat,
            "canary_version": self.version,
            "running": running,
            "queued": queued,
        }


def read_info(workspace_root: Path) -> ServerInfo | None:
    """The server's ``server.lock`` and ``server.json``, or ``None`` if either is missing."""
    directory = server_dir(workspace_root)
    try:
        pid, _, host = (directory / "server.lock").read_text().strip().partition("@")
        data = json.loads((directory / "server.json").read_text())
        return ServerInfo(
            pid=int(pid),
            host=host,
            started=data["started"],
            heartbeat=data["heartbeat"],
            version=data["canary_version"],
            beat=data.get("beat", 0),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def live_server(workspace_root: Path, *, observe: float | None = None) -> ServerInfo | None:
    """The workspace's server if it is alive, else ``None``.

    On the server's own host: its process exists and its heartbeat is fresh (one clock, so
    comparing times is safe).  On any other host the clocks may disagree by more than the
    heartbeat interval, so times are never compared: the server is alive if its ``beat``
    counter advances within *observe* seconds (default ``OBSERVE_FOR``).  That check
    costs up to a few seconds.
    """
    info = read_info(workspace_root)
    if info is None:
        return None
    if info.host == socket.gethostname():
        fresh = time.time() - info.heartbeat <= STALE_AFTER
        return info if fresh and _pid_exists(info.pid) else None
    deadline = time.monotonic() + (OBSERVE_FOR if observe is None else observe)
    while time.monotonic() < deadline:
        time.sleep(0.2)
        now = read_info(workspace_root)
        if now is None:
            return None  # it stopped
        if (now.pid, now.host) != (info.pid, info.host) or now.beat != info.beat:
            return now  # restarted, or beating
    return None


class Server:
    """The server process for one workspace.

    :meth:`run` owns the workspace's server files until it returns: it takes the
    lock, writes the heartbeat, runs requests one at a time (each in a child
    ``canary`` process), and stops on SIGTERM/SIGINT/SIGHUP, on the ``stop`` sentinel, or
    on :meth:`request_stop`.  Stopping interrupts the running request; queued requests
    stay queued for the next server.  If the workspace itself disappears (``canary rm``,
    ``run -w`` or a manual delete), the server kills the running child and exits without
    writing anything, so it never recreates the workspace's directories.
    """

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root)
        self.dir = server_dir(workspace_root)
        self.lock = self.dir / "server.lock"
        self.info_file = self.dir / "server.json"
        self.stop_file = self.dir / "stop"
        self.config_file = self.dir / "config.json"
        self._stop = threading.Event()
        self.info: ServerInfo | None = None
        self._running: _Running | None = None

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Serve until asked to stop."""
        from _canary import config

        from ...api.dispatch import ReadLane
        from ...api.dispatch import build_registry
        from . import inbox

        self._acquire()
        # While it serves, the workspace is in use: `canary rm` and `run -w` refuse.
        in_use = contextlib.ExitStack()
        in_use.enter_context(inuse.using(self.workspace_root))
        previous = self._install_signal_handlers()
        reads: ReadLane | None = None
        try:
            logger.info(
                f"[bold]Canary server[/] running for {self.dir.parent.parent} (pid {os.getpid()})"
            )
            inbox.make_dirs(self.workspace_root)
            self._write_config()
            install_carl(self.workspace_root)
            inbox.prune(self.workspace_root, config.get("server:retain_days", RETAIN_DAYS))
            registry = build_registry()
            reads = ReadLane(
                config.get("server:read_workers", READ_WORKERS),
                config.get("server:read_timeout", READ_TIMEOUT),
            )
            self._recover()
            inbox.recover(self.workspace_root, reads, registry)
            last_heartbeat = 0.0
            while not self._stop.is_set() and not self.stop_file.exists():
                if not self._workspace_exists():
                    self._workspace_gone()
                    return
                if time.time() - last_heartbeat >= HEARTBEAT_INTERVAL:
                    try:
                        self._heartbeat()
                    except FileNotFoundError:
                        self._workspace_gone()
                        return
                    last_heartbeat = time.time()
                    self._cancel_queued()
                try:
                    inbox.accept_inbox(self.workspace_root, reads, registry)
                    reads.check()
                except Exception:
                    logger.exception("Error accepting the inbox")
                if self._running is not None:
                    self._check_running()
                else:
                    self._start_next()
                self._stop.wait(TICK)
        finally:
            if reads is not None:
                reads.shutdown(record=self._workspace_exists())
            if self._running is not None and self._workspace_exists():
                self._interrupt(self._running, reason="server stopped")
            self._release()
            in_use.close()
            self._restore_signal_handlers(previous)
            logger.info("[bold]Canary server[/] stopped")

    def _acquire(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                root = self.dir.parent.parent
                if read_info(root) is None:
                    # A starting server writes server.json right after taking the lock.
                    deadline = time.monotonic() + STALE_AFTER
                    while read_info(root) is None and time.monotonic() < deadline:
                        time.sleep(0.2)
                info = live_server(root)
                if info is not None:
                    raise ServerRunningError(
                        f"a server is already running for this workspace (pid {info.pid} on {info.host})"
                    ) from None
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
        self._heartbeat()  # visible at once to clients and to a competing server

    # ------------------------------------------------------------------ requests

    def _recover(self) -> None:
        """Settle requests a dead server left claimed: running ones failed, others requeued."""
        from ...api import requests

        queue = requests.work_queue(self.workspace_root)
        for path in sorted(queue.claimed.iterdir()):
            try:
                directory = requests.request_dir(self.workspace_root, queue.load(path)["id"])
            except (ValueError, KeyError, OSError):
                queue.fail(path, reason="unreadable request")
                continue
            if requests.read_status(directory).get("state") == "running":
                requests.finish(
                    directory, "failed", reason="the server exited while the request was running"
                )
                queue.ack(path)
            else:
                queue.release(path)

    def _start_next(self) -> None:
        from ...api import requests

        queue = requests.work_queue(self.workspace_root)
        claimed = queue.claim(limit=1)
        if not claimed:
            return
        path = claimed[0]
        try:
            directory = requests.request_dir(self.workspace_root, queue.load(path)["id"])
            request = requests.read_request(directory)
        except (ValueError, KeyError, OSError) as exc:
            queue.fail(path, reason=f"unreadable request: {exc}")
            return
        status = requests.read_status(directory)
        if status.get("state") != "queued" or (directory / "cancel").exists():
            if status.get("state") not in requests.TERMINAL_STATES:
                requests.finish(directory, "cancelled", reason="cancelled")
            queue.ack(path)
            return
        cwd = requests.resolve_cwd(request["cwd"], self.workspace_root)
        if not os.path.isdir(cwd):
            requests.finish(
                directory, "failed", reason=f"working directory {request['cwd']} does not exist"
            )
            queue.ack(path)
            return
        env = dict(os.environ)
        env.update(request.get("env") or {})
        env["PWD"] = cwd  # the server's own $PWD is where it started, not the request's cwd
        env["CANARY_LEVEL"] = "0"
        env["CANARY_SERVER_REQUEST"] = request["id"]
        env[CONFIG_ENV] = str(self.config_file)
        cmd = [sys.executable, "-m", "_canary.service.fs.worker", str(self.workspace_root)]
        cmd.append(request["id"])
        shown = request["path"]
        proc = subprocess.Popen(  # nosec B603
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        requests.write_status(directory, state="running", started=time.time())
        logger.info(f"[bold]Running[/] request {request['id']}: {shown}")
        assert proc.stdout is not None and proc.stderr is not None
        copiers = [
            _copy(proc.stdout, directory / "stdout"),
            _copy(proc.stderr, directory / "stderr"),
        ]
        self._running = _Running(
            proc=proc, path=path, directory=directory, request_id=request["id"], copiers=copiers
        )

    def _check_running(self) -> None:
        from ...api import requests

        running = self._running
        assert running is not None
        if (running.directory / "cancel").exists() and running.proc.poll() is None:
            self._interrupt(running, reason="cancelled")
            return
        code = running.proc.poll()
        if code is None:
            return
        running.finish_output()
        requests.finish(running.directory, "done", returncode=code)
        requests.work_queue(self.workspace_root).ack(running.path)
        self._running = None

    def _interrupt(self, running: "_Running", *, reason: str) -> None:
        """Stop the request's child (SIGINT, then SIGTERM, then SIGKILL) and record it."""
        from ...api import requests

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            if running.proc.poll() is not None:
                break
            try:
                os.killpg(running.proc.pid, sig)
            except ProcessLookupError:
                break
            try:
                running.proc.wait(INTERRUPT_GRACE)
            except subprocess.TimeoutExpired:
                continue
        running.finish_output()
        state = "cancelled" if reason == "cancelled" else "failed"
        requests.finish(running.directory, state, returncode=running.proc.poll(), reason=reason)
        requests.work_queue(self.workspace_root).ack(running.path)
        self._running = None

    def _workspace_exists(self) -> bool:
        return (self.workspace_root / workspace_tag).exists()

    def _workspace_gone(self) -> None:
        """The workspace was removed: kill the running child and record nothing."""
        logger.warning(f"Workspace {self.workspace_root} no longer exists; stopping the server")
        if self._running is not None:
            try:
                os.killpg(self._running.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._running.proc.wait()
            self._running = None

    # ------------------------------------------------------------------ files

    def _cancel_queued(self) -> None:
        """Finish queued requests whose ``cancel`` sentinel appeared (checked each heartbeat)."""
        from ...api import requests

        for request_id in requests.queued_ids(self.workspace_root):
            directory = requests.request_dir(self.workspace_root, request_id)
            if (directory / "cancel").exists():
                requests.finish(directory, "cancelled", reason="cancelled")
                logger.info(f"[bold]Cancelled[/] queued request {request_id}")

    def _heartbeat(self) -> None:
        from ...api import requests

        assert self.info is not None
        self.info.heartbeat = time.time()
        self.info.beat += 1
        queued = len(requests.queued_ids(self.workspace_root))
        doc = self.info.public(running=int(self._running is not None), queued=queued)
        atomic_write(self.info_file, json.dumps(doc, indent=2))

    def _write_config(self) -> None:
        from _canary import config
        from _canary.util import json_helper

        atomic_write(self.config_file, json_helper.dumps(config.snapshot(), indent=2))
        os.chmod(self.config_file, 0o600)

    def _release(self) -> None:
        for path in (self.info_file, self.config_file, self.stop_file, self.lock):
            path.unlink(missing_ok=True)

    def _install_signal_handlers(self) -> dict[int, Any]:
        if threading.current_thread() is not threading.main_thread():
            return {}
        handler = lambda signum, frame: self.request_stop()
        return {
            sig: signal.signal(sig, handler)
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
        }

    @staticmethod
    def _restore_signal_handlers(previous: dict[int, Any]) -> None:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


@dataclasses.dataclass
class _Running:
    """The request the server is running."""

    proc: subprocess.Popen
    path: Path
    directory: Path
    request_id: str
    copiers: list[threading.Thread] = dataclasses.field(default_factory=list)

    def finish_output(self, timeout: float = 10.0) -> None:
        """Wait until the child's output has been copied (its pipes have closed)."""
        for copier in self.copiers:
            copier.join(timeout)


def _copy(pipe: IO[bytes], path: Path) -> threading.Thread:
    """Copy *pipe* to the file *path* until it closes (never to the server's terminal)."""

    def copy() -> None:
        with pipe:
            try:
                out: IO[bytes] | None = open(path, "ab")
            except OSError:
                out = None
            try:
                for chunk in iter(lambda: os.read(pipe.fileno(), 65536), b""):
                    if out is not None:
                        try:
                            out.write(chunk)
                            out.flush()
                        except OSError:
                            out = None  # the workspace went away; keep draining the pipe
            finally:
                if out is not None:
                    out.close()

    thread = threading.Thread(target=copy, daemon=True)
    thread.start()
    return thread


def install_carl(workspace_root: Path) -> Path:
    """Write ``<workspace>/share/carl``: a curl-like client callers can run with only ``sh``.

    Rewritten at every start, so it always matches the server.  See ``carl --help``.
    """
    from importlib import resources

    script = resources.files("_canary.service.fs").joinpath("carl.sh").read_text()
    path = Path(workspace_root) / "share" / "carl"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, script)
    os.chmod(path, 0o755)  # nosec B103: callers run it; it holds no secret
    return path


def stop(workspace_root: Path, *, timeout: float = 3 * INTERRUPT_GRACE + 15.0) -> bool:
    """Ask the workspace's server to stop and wait for it; return False if none was running."""
    info = live_server(workspace_root)
    directory = server_dir(workspace_root)
    if info is None:
        if (directory / "server.lock").exists() and read_info(workspace_root) is not None:
            for name in ("server.json", "config.json", "server.lock", "stop"):
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
