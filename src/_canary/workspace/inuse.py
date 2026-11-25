# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The workspace in-use lock: removal waits for nothing, and refuses while in use.

Anything that writes to a workspace -- a ``canary run``, ``collect``, ``select`` or
``rebaseline``, or a ``canary server`` for its lifetime -- holds a *shared* lock on
``<workspace>/in-use`` (:func:`using`).  Any number may hold it at once.  Removing the
workspace (``canary rm``, ``canary run -w``) needs it *exclusively* (:func:`removing`)
and refuses, without waiting, while anyone holds it.

The lock is ``fcntl.flock``: the kernel drops it when its holder exits, however it
exits (SIGKILL and the out-of-memory killer included), so a dead holder never leaves a
stale lock.  Where ``fcntl`` is unavailable (Windows) the lock is not taken, as with
:func:`~_canary.util.filesystem.locked_file`.  Reads take no lock.
"""

import contextlib
import os
from pathlib import Path
from typing import Generator

#: The lock file, in the workspace directory (no ``.lock`` suffix: the workspace globs
#: ``*.lock`` for job lock files).
LOCK_NAME = "in-use"


class WorkspaceInUseError(ValueError):
    """Raised on removing a workspace that a canary command or server is using."""


@contextlib.contextmanager
def using(workspace_root: str | Path) -> Generator[None, None, None]:
    """Hold the workspace's shared in-use lock while the body runs."""
    with _flock(workspace_root, exclusive=False):
        yield


@contextlib.contextmanager
def removing(workspace_root: str | Path) -> Generator[None, None, None]:
    """Hold the exclusive lock while the body removes the workspace, or refuse at once."""
    with _flock(workspace_root, exclusive=True):
        yield


@contextlib.contextmanager
def _flock(workspace_root: str | Path, *, exclusive: bool) -> Generator[None, None, None]:
    try:
        import fcntl
    except ImportError:
        yield  # no cross-process locking on this platform
        return
    path = Path(workspace_root) / LOCK_NAME
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    except FileNotFoundError:
        yield  # the workspace directory is gone (or not there yet): nothing to guard
        return
    try:
        if exclusive:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise WorkspaceInUseError(
                    f"cannot remove the workspace at {Path(workspace_root).parent}: a canary "
                    "command or server is using it; stop it first (a server: "
                    "'canary server stop')"
                ) from None
        else:
            fcntl.flock(fd, fcntl.LOCK_SH)
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock
