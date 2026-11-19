# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Requests to a workspace's server: building, submitting, inspecting, following.

A request is a canary command line: ``{"command": "run", "args": [...]}`` plus the
global ``options`` that preceded the command, the working directory, and any
environment variables given explicitly.  The command runs in the *server's* environment
(as of ``canary server start``: modules, ``PATH``, ...); no client variables are carried
unless a request names them in ``env``.  Its files live in ``<server dir>/requests/<id>/``:

* ``request.json`` -- the request.
* ``status.json`` -- ``state`` (queued, running, done, cancelled, failed), ``pid``,
  ``returncode``, ``reason``, and ``submitted``/``started``/``finished`` times.
* ``stdout`` / ``stderr`` -- the child's output, appended while it runs.
* ``cancel`` -- sentinel: cancel a queued or running request.

The server's inbox (an :class:`~_canary.util.fsqueue.FSQueue`) carries the requests in
arrival order; the request directory is the source of truth for its state.
"""

import getpass
import json
import os
import secrets
import socket
import sys
import time
from pathlib import Path
from typing import IO
from typing import Any

from _canary import version
from _canary.util.filesystem import atomic_write
from _canary.util.fsqueue import FSQueue

from .server import server_dir

#: Commands the server runs, and for a command with subcommands, which ones.  ``--connect``
#: with anything else is an error.  ``hpc run`` occupies the server while its batches wait
#: on the scheduler (requests run one at a time).
SERVER_COMMANDS: dict[str, tuple[str, ...] | None] = {
    "run": None,
    "exec": None,
    "collect": None,
    "select": None,
    "hpc": ("run",),
}


def server_runs(command: str, args: list[str]) -> bool:
    """True if the server runs ``canary command args``."""
    if command not in SERVER_COMMANDS:
        return False
    subcommands = SERVER_COMMANDS[command]
    return subcommands is None or (bool(args) and args[0] in subcommands)


def server_commands() -> str:
    """The commands the server runs, for messages: ``run, exec, ..., hpc run``."""
    return ", ".join(
        name if subs is None else ", ".join(f"{name} {sub}" for sub in subs)
        for name, subs in SERVER_COMMANDS.items()
    )


TERMINAL_STATES = ("done", "cancelled", "failed")
CANCELLED_RETURNCODE = 130


def inbox(workspace_root: Path) -> FSQueue:
    return FSQueue(server_dir(workspace_root) / "inbox")


def request_dir(workspace_root: Path, request_id: str) -> Path:
    if not request_id or "/" in request_id or request_id.startswith("."):
        raise ValueError(f"invalid request id {request_id!r}")
    return server_dir(workspace_root) / "requests" / request_id


def make_request(
    command: str,
    args: list[str],
    options: list[str] | None = None,
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a complete request for ``canary [options] command [args]``.

    *cwd* is the working directory: relative to the workspace anchor (the directory
    holding ``.canary``), or absolute; default ``"."``, the anchor.  Use
    :func:`relative_cwd` to express a client directory that way.  *env* holds variables
    to set on top of the server's environment; nothing from the client's environment is
    carried otherwise.
    """
    if not server_runs(command, list(args)):
        shown = " ".join([command, *args[:1]])
        raise ValueError(f"the server runs {server_commands()}; {shown!r} runs locally")
    if not all(isinstance(a, str) for a in [*args, *(options or [])]):
        raise ValueError("request args and options must be strings")
    env = dict(env or {})
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ValueError("request env must map variable names to string values")
    return {
        "id": f"{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(3)}",
        "command": command,
        "args": list(args),
        "options": list(options or []),
        "cwd": cwd or ".",
        "env": env,
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "submitted": time.time(),
        "client_version": version.__version__,
    }


def anchor_of(workspace_root: Path) -> Path:
    """The workspace anchor: the directory holding the workspace root (``.canary``)."""
    return Path(workspace_root).parent


def relative_cwd(cwd: str | Path, anchor: str | Path) -> str:
    """*cwd* relative to *anchor*, so it survives a share mounted under different paths.

    Machines can mount the same filesystem at different places (``/projects`` here is
    ``/gpfs/.../dev`` there).  The workspace anchor is what both sides agree on, so the
    request records the client's directory relative to it.  Paths are compared as given
    (symlinks kept: they exist on the shared filesystem too); only when that leaves the
    workspace tree are resolved paths tried instead.
    """
    logical = os.path.relpath(os.path.abspath(cwd), os.path.abspath(anchor))
    if not logical.startswith(".."):
        return logical
    real = os.path.relpath(os.path.realpath(cwd), os.path.realpath(anchor))
    return real if not real.startswith("..") else logical


def client_cwd() -> str:
    """The current directory as the user sees it: ``$PWD`` (symlinks kept) if it is current."""
    cwd = os.getcwd()
    pwd = os.environ.get("PWD")
    try:
        if pwd and os.path.samefile(pwd, cwd):
            return pwd
    except OSError:
        pass
    return cwd


def resolve_cwd(cwd: str, workspace_root: Path) -> str:
    """The request's working directory on this machine (relative paths: from the anchor)."""
    path = cwd if os.path.isabs(cwd) else os.path.join(anchor_of(workspace_root), cwd)
    return os.path.normpath(path)


def submit(workspace_root: Path, request: dict[str, Any]) -> str:
    """Write *request*'s directory, queue it, and return its id."""
    directory = request_dir(workspace_root, request["id"])
    directory.mkdir(parents=True)
    atomic_write(directory / "request.json", json.dumps(request, indent=2))
    write_status(directory, state="queued", submitted=request["submitted"])
    inbox(workspace_root).put({"id": request["id"]})
    return request["id"]


def write_status(directory: Path, **fields: Any) -> dict[str, Any]:
    """Merge *fields* into ``status.json`` and return the new status."""
    status = read_status(directory)
    status.update(fields)
    atomic_write(directory / "status.json", json.dumps(status, indent=2))
    return status


def read_status(directory: Path) -> dict[str, Any]:
    try:
        return json.loads((directory / "status.json").read_text())
    except (OSError, ValueError):
        return {}


def read_request(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "request.json").read_text())


def queued_ids(workspace_root: Path) -> list[str]:
    """Ids of queued requests, oldest first."""
    found: list[tuple[float, str]] = []
    root = server_dir(workspace_root) / "requests"
    if not root.exists():
        return []
    for directory in root.iterdir():
        status = read_status(directory)
        if status.get("state") == "queued":
            found.append((status.get("submitted", 0.0), directory.name))
    return [request_id for _, request_id in sorted(found)]


def running_id(workspace_root: Path) -> str | None:
    root = server_dir(workspace_root) / "requests"
    if not root.exists():
        return None
    for directory in root.iterdir():
        if read_status(directory).get("state") == "running":
            return directory.name
    return None


def get(workspace_root: Path, request_id: str) -> dict[str, Any]:
    """The request's record: what it runs, its status, and where its output is."""
    directory = request_dir(workspace_root, request_id)
    if not directory.exists():
        raise ValueError(f"no request {request_id!r} for this workspace's server")
    request = read_request(directory)
    record: dict[str, Any] = {
        "id": request_id,
        "command": request["command"],
        "args": request["args"],
        "options": request.get("options", []),
        "cwd": request["cwd"],
        **read_status(directory),
        "stdout": str(directory / "stdout"),
        "stderr": str(directory / "stderr"),
    }
    if record.get("state") == "queued":
        queue = queued_ids(workspace_root)
        record["position"] = queue.index(request_id) + 1 if request_id in queue else None
    return record


def cancel(workspace_root: Path, request_id: str) -> str:
    """Cancel a queued or running request; return its state afterwards."""
    directory = request_dir(workspace_root, request_id)
    if not directory.exists():
        raise ValueError(f"no request {request_id!r} for this workspace's server")
    state = read_status(directory).get("state")
    if state in TERMINAL_STATES:
        return state
    (directory / "cancel").touch()
    if state == "queued":
        write_status(directory, state="cancelled", finished=time.time(), reason="cancelled")
        return "cancelled"
    return state or "unknown"


def returncode(status: dict[str, Any]) -> int:
    """The exit code a client reports for a finished request."""
    state = status.get("state")
    if state == "done":
        return int(status.get("returncode") or 0)
    if state == "cancelled":
        return CANCELLED_RETURNCODE
    return 1


def follow(
    workspace_root: Path,
    request_id: str,
    *,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
    quiet: bool = False,
    poll: float = 0.2,
) -> int:
    """Stream the request's output until it finishes; return its exit code.

    Ctrl-C cancels the request (it is reported once it has stopped); a second
    Ctrl-C stops following and leaves the request to the server.
    """
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    directory = request_dir(workspace_root, request_id)
    offsets = {"stdout": 0, "stderr": 0}
    shown_position = None
    cancelled = False

    def drain() -> None:
        for name, stream in (("stdout", out), ("stderr", err)):
            path = directory / name
            if not path.exists():
                continue
            with open(path, errors="replace") as fh:
                fh.seek(offsets[name])
                text = fh.read()
                offsets[name] = fh.tell()
            if text and not quiet:
                stream.write(text)
                stream.flush()

    while True:
        try:
            status = read_status(directory)
            state = status.get("state")
            if state == "queued" and not quiet:
                queue = queued_ids(workspace_root)
                position = queue.index(request_id) + 1 if request_id in queue else None
                if position != shown_position:
                    err.write(f"canary server: request {request_id} queued (position {position})\n")
                    err.flush()
                    shown_position = position
            drain()
            if state in TERMINAL_STATES:
                if state != "done" and not quiet:
                    err.write(
                        f"canary server: request {request_id} {state}: {status.get('reason', '')}\n"
                    )
                return returncode(status)
            time.sleep(poll)
        except KeyboardInterrupt:
            if cancelled:
                err.write(
                    f"canary server: stopped following {request_id}; it may still be running\n"
                )
                return CANCELLED_RETURNCODE
            cancelled = True
            err.write(f"canary server: cancelling {request_id} ...\n")
            cancel(workspace_root, request_id)


def split_command_line(argv: list[str], command: str) -> tuple[list[str], list[str]]:
    """Split ``canary [options] command [args]`` into (options, args).

    ``--connect WHERE`` is dropped (the server runs the command locally) and so is
    ``-C DIR`` (the request carries the resulting working directory instead).  The
    command is the first token equal to *command*; an option value spelled like the
    command name before it would be misread.
    """
    try:
        index = argv.index(command)
    except ValueError as exc:
        raise ValueError(f"{command!r} not found on the command line") from exc
    options: list[str] = []
    before = iter(argv[:index])
    for token in before:
        if token.startswith("--connect="):
            continue
        if token in ("--connect", "-C"):
            next(before, None)
            continue
        if token.startswith("-C") and not token.startswith("--"):
            continue
        options.append(token)
    return options, argv[index + 1 :]
