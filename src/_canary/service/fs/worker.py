# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""``python -m _canary.service.fs.worker ROOT ID``: run one work request, in its own process.

The server starts one worker per work request (one at a time) in the request's cwd,
captures its output, and signals it to cancel.  The worker restores the server's
configuration snapshot, so it starts up exactly as ``canary server start`` did.  The worker validates the stored request
against its endpoint's model and calls the handler, which works through ``_canary.app``
(no command line).  What the handler returns is the result's ``data``; a
:class:`~_canary.api.dispatch.RequestError` or an exception becomes its error.  The
worker reports either in ``.outcome.json``, which the server merges into
``result.json``.
"""

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

#: Exit codes of a worker whose handler raised.
REJECTED, FAILED = 2, 1


def main(argv: list[str] | None = None) -> int:
    root, request_id = argv if argv is not None else sys.argv[1:]
    from _canary import config
    from _canary.util.filesystem import atomic_write
    from _canary.workspace.workspace import set_workspace_dir

    from ...api import requests
    from ...api.dispatch import Context
    from ...api.dispatch import RequestError
    from ...api.dispatch import build_registry
    from . import server

    # Start up as the server did (its snapshot), like every canary child.  The variable is
    # dropped first so the processes a run starts (its tests) never see it.
    if snapshot := os.environ.pop(server.CONFIG_ENV, None):
        config.load_snapshot(json.loads(Path(snapshot).read_text()))
    workspace_root = Path(root)
    set_workspace_dir(workspace_root)  # every Workspace.load() here is the server's
    directory = requests.request_dir(workspace_root, request_id)
    record = requests.read_request(directory)
    registry = build_registry()
    endpoint = registry.get(record["path"])
    assert endpoint is not None and endpoint.lane == "work", record["path"]
    body = endpoint.model.model_validate(record["request"])
    ctx = Context(
        workspace_root, request_id, record["user"], record["cwd"], record["submitted"], registry
    )

    def report(**outcome: Any) -> None:
        atomic_write(directory / ".outcome.json", json.dumps(outcome))

    try:
        data = endpoint.func(body, ctx)
    except RequestError as exc:
        sys.stderr.write(f"{endpoint.path}: {exc}\n")
        report(status_code=exc.status_code, error=str(exc))
        return REJECTED
    except Exception as exc:
        traceback.print_exc()
        report(status_code=500, error=f"{type(exc).__name__}: {exc}")
        return FAILED
    report(status_code=200, data=data)
    # Work that ran reports its own exit code (``data.exit_code``); the worker exits with it.
    return int(data.get("exit_code", 0)) if isinstance(data, dict) else 0


if __name__ == "__main__":
    sys.exit(main())
