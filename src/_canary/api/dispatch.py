# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Endpoints, and the one path every request takes.

Endpoints register through the ``canary_addendpoint`` hook, core and plugin alike (as
commands do through ``canary_addcommand``)::

    @hookimpl(specname="canary_addendpoint")
    def query_endpoints(registry: EndpointRegistry) -> None:
        registry.register("/canary/status", status)
        registry.register("/canary/select", select, lane="work")

The request model comes from the handler's ``request`` annotation.  A *read* handler runs
in the server (:class:`ReadLane`); a *work* handler runs in a worker child, one at a time
(:mod:`_canary.service.fs.worker`).  Either returns the result's ``data``.  Handlers are
plain synchronous functions of a validated model and a :class:`Context`, and never know
which server (files now, HTTP later) received the request.

:func:`accept` takes a request by id from any transport (the inbox today, HTTP later):
it validates the envelope, routes it, and either queues it (work) or executes it (read).
"""

import concurrent.futures
import dataclasses
import functools
import json
import os
import re
import threading
import time
import typing
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from typing import Callable
from typing import Literal

from pydantic import BaseModel
from pydantic import ValidationError

from ..util import logging
from ..util.filesystem import atomic_write
from . import requests
from .models import Envelope
from .models import Result
from .models import State

if typing.TYPE_CHECKING:
    from ..workspace.workspace import Workspace

logger = logging.get_logger(__name__)

Lane = Literal["work", "read"]

#: A request id: chosen by the caller, safe as a file name.
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RequestError(Exception):
    """Raised by a handler to answer with a 4xx (the caller's mistake) instead of a 500."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclasses.dataclass
class Context:
    """What a handler knows about the request besides its body."""

    workspace_root: Path
    id: str
    user: str
    #: Working directory, relative to the anchor.
    cwd: str
    submitted: float
    #: The endpoints of the server that received the request.
    registry: "EndpointRegistry | None" = None

    @property
    def anchor(self) -> Path:
        """The directory holding the workspace root; public paths are relative to it."""
        return self.workspace_root.parent

    @functools.cached_property
    def workspace(self) -> "Workspace":
        """The workspace, loaded on first use (in the thread that runs the handler)."""
        from ..workspace.workspace import Workspace

        return Workspace.load(self.workspace_root)

    def interrupt(self) -> None:
        """Abort the handler's database statement, if it has one running."""
        workspace = self.__dict__.get("workspace")
        if workspace is not None:
            workspace.db.interrupt()

    def close(self) -> None:
        workspace = self.__dict__.pop("workspace", None)
        if workspace is not None:
            workspace.db.close()


@dataclasses.dataclass(frozen=True)
class Endpoint:
    path: str
    lane: Lane
    model: type[BaseModel]
    func: Callable[[Any, Context], Any]


class EndpointRegistry:
    """Routes to handlers.  Filled by the ``canary_addendpoint`` hook (:func:`build_registry`)."""

    def __init__(self) -> None:
        self._endpoints: dict[str, Endpoint] = {}

    def register(self, path: str, func: Callable, *, lane: Lane = "read") -> None:
        """Route *path* to *func*; its ``request`` annotation is the body's model."""
        model = typing.get_type_hints(func).get("request")
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise TypeError(f"{func!r}: 'request' must be annotated with a pydantic model")
        if lane not in ("read", "work"):
            raise ValueError(f"{path}: lane must be 'read' or 'work', not {lane!r}")
        if (other := self._endpoints.get(path)) is not None:
            raise ValueError(
                f"endpoint {path} is already registered "
                f"(by {other.func.__module__}; again by {func.__module__})"
            )
        self._endpoints[path] = Endpoint(path, lane, model, func)

    def get(self, path: str) -> Endpoint | None:
        return self._endpoints.get(path)

    def __iter__(self) -> typing.Iterator[Endpoint]:
        return iter(sorted(self._endpoints.values(), key=lambda e: e.path))


def build_registry() -> EndpointRegistry:
    """Every endpoint core and the plugins register (``canary_addendpoint``)."""
    from .. import config

    registry = EndpointRegistry()
    config.pluginmanager.hook.canary_addendpoint(registry=registry)
    return registry


def accept(
    request_id: str,
    envelope: Any,
    *,
    user: str,
    workspace_root: Path,
    registry: EndpointRegistry | None = None,
    reads: "ReadLane | None" = None,
) -> Result | None:
    """Take request *request_id*: queue it (work) or execute it (read).

    *envelope* is the parsed envelope, or its JSON text.

    Returns the result if the request is finished (rejected, or a read run here), or
    ``None`` if it was queued: work for the server's child, a read on *reads*.  A finished request's ``result.json`` is written, except for a
    duplicate id (``409``): that directory belongs to the earlier request.  Raises
    ``ValueError`` if *request_id* is not a valid id (there is nowhere to answer).
    """
    if not isinstance(request_id, str) or not REQUEST_ID.match(request_id):
        raise ValueError(f"invalid request id {request_id!r}")
    registry = build_registry() if registry is None else registry
    workspace_root = Path(workspace_root)
    submitted = time.time()
    ctx = Context(workspace_root, request_id, user, ".", submitted, registry)
    bad_json: str | None = None
    if isinstance(envelope, (str, bytes)):
        try:
            envelope = json.loads(envelope)
        except ValueError as exc:
            bad_json = f"invalid JSON: {exc}"
    path = envelope.get("path", "") if isinstance(envelope, dict) else ""
    path = path if isinstance(path, str) else ""

    directory = requests.request_dir(workspace_root, request_id)
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()  # claims the id: exclusive, so a request never runs twice
    except FileExistsError:
        return _rejected(ctx, path, 409, f"request {request_id} already exists")

    def reject(status_code: int, message: str) -> Result:
        result = _rejected(ctx, path, status_code, message)
        requests.write_result(directory, result)
        return result

    if bad_json is not None:
        return reject(400, bad_json)
    try:
        env = Envelope.model_validate(envelope)
    except ValidationError as exc:
        return reject(400, f"invalid envelope: {_errors(exc)}")
    endpoint = registry.get(env.path)
    if endpoint is None:
        return reject(404, f"no endpoint {env.path}")
    try:
        ctx.cwd = _check_cwd(env.cwd, ctx.anchor)
        body = endpoint.model.model_validate(env.request)
    except RequestError as exc:
        return reject(exc.status_code, str(exc))
    except ValidationError as exc:
        return reject(400, f"invalid request for {env.path}: {_errors(exc)}")

    if endpoint.lane == "read":
        if reads is not None:
            requests.write_status(directory, state="queued", submitted=submitted)
            reads.submit(endpoint, body, ctx, directory)
            return None
        requests.write_status(directory, state="running", submitted=submitted, started=time.time())
        try:
            result = execute(endpoint, body, ctx)
        finally:
            ctx.close()
        requests.write_result(directory, result)
        requests.write_status(directory, state=result.state, finished=result.finished)
        return result

    record = {
        "id": request_id,
        "path": env.path,
        "request": body.model_dump(mode="json"),
        "cwd": ctx.cwd,
        "env": env.env,
        "user": user,
        "submitted": submitted,
    }
    atomic_write(directory / "request.json", json.dumps(record, indent=2))
    requests.write_status(directory, state="queued", submitted=submitted)
    requests.work_queue(workspace_root).put({"id": request_id})
    return None


def execute(endpoint: Endpoint, body: BaseModel, ctx: Context) -> Result:
    """Run a read handler: the one place that times requests and turns errors into codes."""
    started = time.time()
    data: Any = None
    error: str | None = None
    try:
        data = endpoint.func(body, ctx)
        status_code, state = 200, "done"
    except RequestError as exc:
        status_code, state, error = exc.status_code, "rejected", str(exc)
    except Exception as exc:
        logger.exception(f"{endpoint.path} failed for request {ctx.id}")
        status_code, state, error = 500, "failed", f"{type(exc).__name__}: {exc}"
    return Result(
        id=ctx.id,
        path=endpoint.path,
        status_code=status_code,
        state=state,
        data=data,
        error=error,
        cwd=ctx.cwd,
        user=ctx.user,
        submitted=ctx.submitted,
        started=started,
        finished=time.time(),
    )


class ReadLane:
    """Reads in up to *workers* threads, each limited to *timeout* seconds once started.

    A thread cannot be killed: a read past its time limit, or cancelled with the
    request's ``cancel`` sentinel, gets its result at once, its database statement is
    interrupted, and whatever the thread returns later is dropped.  :meth:`check` (on
    every server tick) enforces both.
    """

    def __init__(self, workers: int, timeout: float) -> None:
        self.timeout = timeout
        self._pool = concurrent.futures.ThreadPoolExecutor(workers, thread_name_prefix="read")
        self._lock = threading.Lock()
        self._reads: dict[str, _Read] = {}

    def submit(self, endpoint: Endpoint, body: BaseModel, ctx: Context, directory: Path) -> None:
        read = _Read(endpoint, body, ctx, directory)
        with self._lock:
            self._reads[ctx.id] = read
        read.future = self._pool.submit(self._run, read)

    def check(self) -> None:
        """Settle reads that were cancelled or ran past the time limit."""
        now = time.time()
        with self._lock:
            reads = list(self._reads.values())
        for read in reads:
            if (read.directory / "cancel").exists():
                self._stop(read, "cancelled", 499, "cancelled")
            elif read.started is not None and now - read.started > self.timeout:
                self._stop(read, "failed", 500, f"exceeded the read time limit of {self.timeout} s")

    def shutdown(self, *, record: bool = True) -> None:
        """Fail every unfinished read (unless not *record*ing: the workspace is gone)."""
        with self._lock:
            reads = list(self._reads.values())
        for read in reads:
            if record:
                self._stop(read, "failed", 500, "server stopped")
            else:
                read.settled = True
                read.ctx.interrupt()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _run(self, read: "_Read") -> None:
        with read.lock:
            if read.settled:
                return
            read.started = time.time()
            requests.write_status(read.directory, state="running", started=read.started)
        try:
            result = execute(read.endpoint, read.body, read.ctx)
        finally:
            read.ctx.close()
        self._settle(read, result)

    def _stop(self, read: "_Read", state: State, status_code: int, reason: str) -> None:
        if read.future is not None:
            read.future.cancel()  # not started yet: it never will
        read.ctx.interrupt()
        result = Result(
            id=read.ctx.id,
            path=read.endpoint.path,
            status_code=status_code,
            state=state,
            error=reason,
            cwd=read.ctx.cwd,
            user=read.ctx.user,
            submitted=read.ctx.submitted,
            started=read.started,
            finished=time.time(),
        )
        self._settle(read, result)

    def _settle(self, read: "_Read", result: Result) -> bool:
        """Write *read*'s result unless it already has one; True if this call wrote it."""
        with read.lock:
            if read.settled:
                return False
            read.settled = True
            requests.write_result(read.directory, result)
            requests.write_status(read.directory, state=result.state, finished=result.finished)
        with self._lock:
            self._reads.pop(read.ctx.id, None)
        return True


@dataclasses.dataclass
class _Read:
    endpoint: Endpoint
    body: BaseModel
    ctx: Context
    directory: Path
    future: concurrent.futures.Future | None = None
    started: float | None = None
    settled: bool = False
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)


def _rejected(ctx: Context, path: str, status_code: int, message: str) -> Result:
    return Result(
        id=ctx.id,
        path=path,
        status_code=status_code,
        state="rejected",
        error=message,
        cwd=ctx.cwd,
        user=ctx.user,
        submitted=ctx.submitted,
        finished=time.time(),
    )


def _check_cwd(cwd: str, anchor: Path) -> str:
    """*cwd* normalized, if it is a directory inside *anchor* (symlinks resolved)."""
    parts = PurePosixPath(cwd)
    if parts.is_absolute() or ".." in parts.parts:
        raise RequestError(400, f"cwd must be relative to the anchor, without '..': {cwd!r}")
    root = os.path.realpath(anchor)
    real = os.path.realpath(os.path.join(root, cwd))
    if real != root and not real.startswith(root + os.sep):
        raise RequestError(400, f"cwd {cwd!r} leads outside the anchor")
    if not os.path.isdir(real):
        raise RequestError(400, f"cwd {cwd!r} is not a directory")
    return os.path.normpath(cwd)


def _errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'body'}: {e['msg']}" for e in exc.errors()
    )
