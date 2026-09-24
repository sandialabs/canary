# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Run a session in a child process, streaming its events to the parent.

The in-process :func:`_canary.app.run.run` owns the terminal (a live console
reporter), the current working directory (``Session.run`` chdirs), and signal
handling.  An interface that wants to *host* a run -- keeping its own display
alive and reacting to live progress -- therefore cannot call it directly on its
main thread, and cannot safely call it on a background thread either (the chdir
and signal handling are process-global).

:func:`run_in_subprocess` runs the session in a separate process instead.  The
child publishes its job-lifecycle events to a durable, file-system-backed spool
(:class:`~_canary.events.SpoolBus`); the parent runs a
:class:`~_canary.events.SpoolListener` that republishes them onto the
application :class:`~_canary.events.EventBus`, so existing subscribers (the TUI
today) observe the child's progress as if it were local.  The spool is used
instead of a :class:`multiprocessing.Queue` because a file-backed queue has no
background feeder thread and so lets the child exit cleanly regardless of how
fast the parent drains -- the same reason Canary funnels test results to the
single database writer through an ``FSQueue``.

The database's single-writer discipline is preserved: the child is its own
``canary_level == 0`` process and owns the writer for its session; the parent
only reads.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..events import SpoolBus
from ..events import SpoolListener
from .facade import get_event_bus

if TYPE_CHECKING:
    from .run import RunOptions


def _child_main(
    spool_dir: str,
    config_snapshot: dict[str, Any],
    request_dict: dict[str, Any],
    options: "RunOptions | None",
) -> None:
    """Entry point in the child process: reconstruct state, run, spool events.

    Must be a module-level function so it is importable by a ``spawn`` start
    method.  Restores the parent's config snapshot, forces the non-interactive
    (event-only) reporter and redirects stdout/stderr so the child never writes
    to the shared terminal, installs a spool forwarder on the child's bus, and
    executes the run.  The run's exit code is returned via ``sys.exit`` so the
    parent reads it from the process exit code -- no in-band control channel.
    """
    import sys

    from .. import config
    from ..app.pathspec import RequestNode
    from ..app.run import run as run_session

    # The parent interface renders from events and the database, so the child's
    # own textual output (event/live tables, the final results summary, banners)
    # must not reach the shared terminal.  Redirect the OS-level stdout/stderr
    # file descriptors for the whole child.
    devnull = open(os.devnull, "w")  # noqa: SIM115 - lives for the process
    try:
        os.dup2(devnull.fileno(), 1)
        os.dup2(devnull.fileno(), 2)
    except OSError:
        pass

    return_code = 1
    try:
        # Belt and braces: also select the non-live reporter.
        os.environ["CANARY_LIVE"] = "0"
        config.load_snapshot(config_snapshot)

        # Forward every event the run publishes on this process's bus to the
        # spool the parent is draining.
        get_event_bus().subscribe(SpoolBus(spool_dir).forward)

        request = RequestNode(kind=request_dict["kind"], value=request_dict["value"])
        return_code = run_session(request, options)
    except BaseException:  # noqa: BLE001 - map any failure to a nonzero exit code
        return_code = 1
    sys.exit(int(return_code) if return_code is not None else 0)


class RunHandle:
    """A running child session and the listener streaming its events.

    Returned by :func:`run_in_subprocess`.  Call :meth:`wait` to block for
    completion and get the exit code, or :meth:`poll` to check without blocking.
    :meth:`terminate` stops the child (used by a future cancel action).  The
    parent-side :class:`~_canary.events.SpoolListener` is started for you and
    stopped -- after a final drain -- when the run ends.
    """

    def __init__(
        self, process: "mp.process.BaseProcess", listener: SpoolListener, spool_dir: Path
    ) -> None:
        self._process = process
        self._listener = listener
        self._spool_dir = spool_dir
        self._returncode: int | None = None

    def poll(self) -> int | None:
        """Return the exit code if the child has finished, else ``None``."""
        if self._returncode is not None:
            return self._returncode
        if self._process.is_alive():
            return None
        self._finish()
        return self._returncode

    def wait(self, timeout: float | None = None) -> int | None:
        """Block until the child finishes (or *timeout*), returning its exit code."""
        self._process.join(timeout=timeout)
        if self._process.is_alive():
            return None
        self._finish()
        return self._returncode

    def _finish(self) -> None:
        if self._returncode is not None:
            return
        code = self._process.exitcode
        self._returncode = code if code is not None else 1
        # Stop after a final drain so the last events (e.g. the terminal
        # job_finished) are delivered, then clean the spool directory up.
        self._listener.stop()
        self._cleanup_spool()

    def _cleanup_spool(self) -> None:
        import shutil

        shutil.rmtree(self._spool_dir, ignore_errors=True)

    def terminate(self) -> None:
        """Terminate the child and stop the listener (best-effort cancellation)."""
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(timeout=1.0)
        self._finish()


def run_in_subprocess(request: Any, options: "RunOptions | None" = None) -> RunHandle:
    """Run *request* in a child process and stream its events to the app bus.

    Args:
        request: A run request (see :func:`_canary.app.run.run`); must expose
            ``kind`` and ``value`` and be picklable.
        options: Run filters/settings; must be picklable.

    Returns:
        A :class:`RunHandle` for awaiting completion and observing progress.
        Events are already flowing onto :func:`get_event_bus` before this
        returns, so an interface only needs to subscribe there.
    """
    from .. import config

    # A private spool directory for this run's events.  Placed under the
    # workspace tmp area when known, else a system temp dir.
    spool_dir = Path(tempfile.mkdtemp(prefix="canary-events-"))

    snapshot = config.snapshot()
    request_dict = {"kind": request.kind, "value": request.value}

    listener = SpoolListener(spool_dir, get_event_bus())
    listener.start()

    ctx = mp.get_context("spawn")
    process = ctx.Process(
        target=_child_main,
        args=(str(spool_dir), snapshot, request_dict, options),
        name="canary-run",
        daemon=False,
    )
    process.start()
    return RunHandle(process, listener, spool_dir)
