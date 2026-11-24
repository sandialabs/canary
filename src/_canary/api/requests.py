# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""A request's files, in ``<server dir>/requests/<id>/`` (the server is their only writer).

* ``request.json`` -- the accepted request: route, validated body, cwd (relative to the
  anchor), env, user and submission time.
* ``status.json`` -- ``state`` (queued, running, done, rejected, cancelled, failed),
  ``returncode``, ``reason``, and ``submitted``/``started``/``finished`` times.
* ``stdout`` / ``stderr`` -- a work request's output, appended while it runs.
* ``cancel`` -- sentinel (written by the caller): cancel a queued or running request.
* ``result.json`` -- the result document, written once, last.

Work requests wait in the server's private queue (an :class:`~_canary.util.fsqueue.FSQueue`,
``queue/``) in arrival order; the request directory is the source of truth for state.
"""

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..util import logging
from ..util.filesystem import atomic_write
from ..util.fsqueue import FSQueue

if TYPE_CHECKING:
    from .models import Result
    from .models import State


logger = logging.get_logger(__name__)

TERMINAL_STATES = ("done", "rejected", "cancelled", "failed")


def server_dir(workspace_root: Path) -> Path:
    """Return the directory holding a workspace's server files."""
    return Path(workspace_root) / "var" / "server"


def work_queue(workspace_root: Path) -> FSQueue:
    """The server's private queue of accepted work requests, in arrival order."""
    return FSQueue(server_dir(workspace_root) / "queue")


def request_dir(workspace_root: Path, request_id: str) -> Path:
    if not request_id or "/" in request_id or request_id.startswith("."):
        raise ValueError(f"invalid request id {request_id!r}")
    return server_dir(workspace_root) / "requests" / request_id


def anchor_of(workspace_root: Path) -> Path:
    """The workspace anchor: the directory holding the workspace root (``.canary``)."""
    return Path(workspace_root).parent


def resolve_cwd(cwd: str, workspace_root: Path) -> str:
    """The request's working directory on this machine (relative paths: from the anchor)."""
    path = cwd if os.path.isabs(cwd) else os.path.join(anchor_of(workspace_root), cwd)
    return os.path.normpath(path)


def write_result(directory: Path, result: "Result") -> None:
    """Write ``result.json`` atomically.  A request has one result: a second is an error."""
    file = directory / "result.json"
    if file.exists():
        raise RuntimeError(f"request {result.id} already has a result")
    atomic_write(file, result.model_dump_json(indent=2) + "\n")
    logger.info(access_line(result))


def access_line(result: "Result") -> str:
    """The server log's one line for *result*: what came back, not the request's output."""
    started = result.started if result.started is not None else result.submitted
    line = (
        f"[bold]{result.status_code}[/] {result.path} {result.id} ({result.user}) "
        f"{result.state} in {result.finished - started:.1f}s"
    )
    if isinstance(result.data, dict) and "exit_code" in result.data:
        line += f", exit code {result.data['exit_code']}"
    if result.error:
        line += f": {result.error}"
    return line


#: The status code of each final state of a work request.
STATUS_CODES = {"done": 200, "cancelled": 499, "failed": 500}


def finish(
    directory: Path, state: "State", *, returncode: int | None = None, reason: str | None = None
) -> None:
    """Record a work request's final *state*: ``status.json``, then ``result.json`` (last)."""
    from .models import Result

    # A worker reports its handler's data, or error, in .outcome.json.
    outcome = _read_json(directory / ".outcome.json") if state == "done" else None
    status_code = STATUS_CODES[state]
    data: Any = None if returncode is None else {"exit_code": returncode}
    if outcome is not None:
        status_code = outcome.get("status_code", status_code)
        if status_code != 200:
            state = "rejected" if status_code < 500 else "failed"
            reason = outcome.get("error")
        elif isinstance(outcome.get("data"), dict):
            data = {**outcome["data"], **(data or {})}
    status = write_status(
        directory, state=state, returncode=returncode, reason=reason, finished=time.time()
    )
    try:
        request = read_request(directory)
    except (OSError, ValueError):
        request = {}
    write_result(
        directory,
        Result(
            id=directory.name,
            path=request.get("path") or f"/canary/{request.get('command', '')}",
            status_code=status_code,
            state=state,
            data=data,
            error=None if state == "done" else reason,
            cwd=request.get("cwd", "."),
            user=request.get("user", ""),
            submitted=status.get("submitted") or status["finished"],
            started=status.get("started"),
            finished=status["finished"],
        ),
    )


def write_status(directory: Path, **fields: Any) -> dict[str, Any]:
    """Merge *fields* into ``status.json`` and return the new status."""
    status = read_status(directory)
    status.update(fields)
    atomic_write(directory / "status.json", json.dumps(status, indent=2))
    return status


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


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
