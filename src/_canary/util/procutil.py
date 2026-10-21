# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Process-tree termination and lifetime helpers.

Canary runs every test in its own session (``start_new_session=True``) so that
a test's own children can be signalled as a group and so that terminal signals
are not delivered to tests directly.  The flip side is that *nothing* kills a
test automatically when canary (or one of its worker processes) goes away; the
helpers here make sure every termination path reaps the whole tree.
"""

import os
import signal
import sys
import threading
import time
from typing import Any
from typing import Iterable

import psutil

from . import logging

logger = logging.get_logger(__name__)


def kill_grace_period() -> float:
    """Seconds to wait between SIGTERM and SIGKILL (``CANARY_KILL_GRACE``, default 2)."""
    try:
        return max(0.0, float(os.getenv("CANARY_KILL_GRACE", "2.0")))
    except ValueError:
        return 2.0


def _signal_group(pgid: int, signum: int) -> None:
    if not hasattr(os, "killpg") or pgid <= 1:
        return
    try:
        os.killpg(pgid, signum)
    except (ProcessLookupError, PermissionError):
        pass
    except OSError as e:  # pragma: no cover - defensive
        logger.debug("killpg(%s, %s) failed: %s", pgid, signum, e)


def _groups_of(procs: Iterable[psutil.Process]) -> set[int]:
    groups: set[int] = set()
    if not hasattr(os, "getpgid"):
        return groups
    own = os.getpgrp()
    for p in procs:
        try:
            pgid = os.getpgid(p.pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
        # Never signal our own process group (which, for workers and inner job
        # processes, is shared with the main canary process and the terminal).
        if pgid > 1 and pgid != own:
            groups.add(pgid)
    return groups


def kill_process_tree(
    pid: int,
    *,
    sig: int = signal.SIGTERM,
    grace: float | None = None,
    include_parent: bool = True,
    create_time: float | None = None,
) -> None:
    """Terminate *pid* and all of its descendants, escalating to SIGKILL.

    Descendants are discovered via :mod:`psutil` *and* via the process groups
    they lead, so tests running in their own session (and anything they spawn
    into that session, even after re-parenting) are reaped as well.

    Args:
        pid: Root of the tree.
        sig: Initial signal (default ``SIGTERM``).
        grace: Seconds to wait before escalating to ``SIGKILL``; defaults to
            :func:`kill_grace_period`.
        include_parent: Also signal *pid* itself.
        create_time: If given, only act if *pid* still refers to the process
            created at this time (guards against PID reuse).
    """
    grace = kill_grace_period() if grace is None else grace
    try:
        root = psutil.Process(pid)
        if create_time is not None and abs(root.create_time() - create_time) > 1e-3:
            return
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return
    try:
        procs = root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        procs = []
    if include_parent:
        procs.append(root)
    groups = _groups_of(procs)

    for p in procs:
        try:
            p.send_signal(sig)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    for g in groups:
        _signal_group(g, sig)

    try:
        _, alive = psutil.wait_procs(procs, timeout=grace)
    except Exception:  # pragma: no cover - defensive
        alive = procs

    kill = getattr(signal, "SIGKILL", signal.SIGTERM)
    for g in groups:
        _signal_group(g, kill)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if alive:
        try:
            psutil.wait_procs(alive, timeout=1.0)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("wait_procs after SIGKILL failed: %s", e)


def kill_session_leader(pid: int, *, grace: float | None = None) -> None:
    """Terminate a process started with ``start_new_session=True`` and its group."""
    kill_process_tree(pid, grace=grace, include_parent=True)
    # The group may contain processes that were re-parented away from *pid*
    # (e.g. daemonized helpers); they still belong to the session's group.
    _signal_group(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


def set_parent_death_signal(signum: int = signal.SIGTERM) -> None:
    """Ask the kernel to send *signum* to this process when its parent exits (Linux only).

    Must be called from the child.  Note that the signal is delivered when the
    *thread* that created this process exits, so the parent must spawn children
    from a long-lived thread (canary spawns from the main thread).
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        PR_SET_PDEATHSIG = 1
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, int(signum), 0, 0, 0)
    except Exception as e:  # pragma: no cover - best effort
        logger.debug("prctl(PR_SET_PDEATHSIG) failed: %s", e)


class ParentWatcher:
    """Detect that the process which started us has gone away (portable fallback)."""

    def __init__(self) -> None:
        self.ppid = os.getppid()

    def parent_alive(self) -> bool:
        return os.getppid() == self.ppid


def install_termination_handlers(signums: Iterable[int], handler: Any) -> dict[int, Any]:
    """Install *handler* for each available signal in *signums*; return the previous handlers.

    No-op (returns ``{}``) when not called from the main thread.
    """
    previous: dict[int, Any] = {}
    if threading.current_thread() is not threading.main_thread():
        return previous
    for signum in signums:
        try:
            previous[signum] = signal.signal(signum, handler)
        except (ValueError, OSError):  # pragma: no cover - unsupported signal
            continue
    return previous


def restore_handlers(previous: dict[int, Any]) -> None:
    for signum, handler in previous.items():
        try:
            signal.signal(signum, handler)
        except (ValueError, OSError, TypeError):  # pragma: no cover
            pass


def termination_signals() -> list[int]:
    """Signals that should trigger an orderly shutdown (those available on this platform)."""
    names = ("SIGTERM", "SIGHUP")
    return [getattr(signal, n) for n in names if hasattr(signal, n)]


def wait_for(predicate, timeout: float, interval: float = 0.05) -> bool:
    """Poll *predicate* until it is true or *timeout* elapses; return its final value."""
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return bool(predicate())
        time.sleep(interval)
