# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""The file binding: requests arrive as ``inbox/<id>.json`` and answer in ``requests/<id>/``.

A caller writes ``inbox/<id>.json.tmp`` and renames it to ``inbox/<id>.json``.  Each tick
the server takes the inbox oldest first: it renames the file into its private
``accepting/`` directory, calls :func:`~_canary.api.dispatch.accept` with the file's
owner as the user, and deletes it.  If the server dies between the rename and the
delete, :func:`recover` settles the leftover at the next start.  A file whose name is
not a valid id, or whose id is taken, moves to ``rejected/<name>`` with
``rejected/<name>.reason`` next to it.
"""

import os
import pwd
import shutil
import time
from pathlib import Path

from _canary.util import logging

from ...api import requests
from ...api.dispatch import REQUEST_ID
from ...api.dispatch import EndpointRegistry
from ...api.dispatch import ReadLane
from ...api.dispatch import accept
from ...api.requests import server_dir

logger = logging.get_logger(__name__)

#: Mode of the directories callers write to (``inbox/``) or read (``rejected/``).
SHARED_MODE = 0o775


def make_dirs(workspace_root: Path) -> None:
    """Create ``inbox/``, ``rejected/`` and ``accepting/``."""
    sdir = server_dir(workspace_root)
    for name in ("inbox", "rejected"):
        (sdir / name).mkdir(parents=True, exist_ok=True)
        os.chmod(sdir / name, SHARED_MODE)  # mkdir's mode is masked by the umask
    (sdir / "accepting").mkdir(exist_ok=True)


def accept_inbox(
    workspace_root: Path, reads: ReadLane | None = None, registry: EndpointRegistry | None = None
) -> int:
    """Accept every ``inbox/*.json``, oldest first; return how many were taken."""
    inbox = server_dir(workspace_root) / "inbox"
    found: list[tuple[int, str]] = []
    try:
        entries = list(os.scandir(inbox))
    except FileNotFoundError:
        return 0
    for entry in entries:
        if entry.name.endswith(".json"):  # *.json.tmp is still being written
            try:
                found.append((entry.stat().st_mtime_ns, entry.name))
            except FileNotFoundError:
                continue
    for _, name in sorted(found):
        take(workspace_root, inbox / name, reads, registry)
    return len(found)


def take(
    workspace_root: Path,
    file: Path,
    reads: ReadLane | None = None,
    registry: EndpointRegistry | None = None,
) -> None:
    """Accept one inbox file."""
    sdir = server_dir(workspace_root)
    request_id = file.name.removesuffix(".json")
    if not REQUEST_ID.match(request_id):
        _reject(
            sdir,
            file,
            f"{file.name!r}: the file name must be <id>.json, with id matching {REQUEST_ID.pattern}",
        )
        return
    try:
        user = _owner(file)
        claimed = sdir / "accepting" / file.name
        os.rename(file, claimed)
    except FileNotFoundError:
        return  # taken away by the caller
    _accept_claimed(workspace_root, claimed, user, reads, registry)


def recover(
    workspace_root: Path, reads: ReadLane | None = None, registry: EndpointRegistry | None = None
) -> None:
    """Settle files a dead server left in ``accepting/``.

    If the request's directory exists, ``accept`` had claimed it, so the file is a
    leftover and is deleted.  Otherwise it never got that far and is accepted now.
    """
    accepting = server_dir(workspace_root) / "accepting"
    if not accepting.is_dir():
        return
    for claimed in sorted(accepting.glob("*.json")):
        request_id = claimed.name.removesuffix(".json")
        if requests.request_dir(workspace_root, request_id).exists():
            logger.debug(f"Removing accepted leftover {claimed}")
            claimed.unlink(missing_ok=True)
        else:
            _accept_claimed(workspace_root, claimed, _owner(claimed), reads, registry)


def prune(workspace_root: Path, retain_days: float) -> None:
    """Remove finished requests, and ``rejected/`` entries, older than *retain_days*."""
    sdir = server_dir(workspace_root)
    cutoff = time.time() - retain_days * 86400
    root = sdir / "requests"
    for directory in root.iterdir() if root.is_dir() else []:
        try:
            if (directory / "result.json").stat().st_mtime < cutoff:
                shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            continue  # unfinished (no result yet)
    rejected = sdir / "rejected"
    for path in rejected.iterdir() if rejected.is_dir() else []:
        try:
            if path.lstat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def _accept_claimed(
    workspace_root: Path,
    claimed: Path,
    user: str,
    reads: ReadLane | None,
    registry: EndpointRegistry | None = None,
) -> None:
    sdir = server_dir(workspace_root)
    request_id = claimed.name.removesuffix(".json")
    try:
        body = claimed.read_bytes()
    except FileNotFoundError:
        return
    result = accept(
        request_id, body, user=user, workspace_root=workspace_root, registry=registry, reads=reads
    )
    if result is not None and result.status_code == 409:
        _reject(sdir, claimed, result.error or "duplicate id")
        return
    claimed.unlink(missing_ok=True)
    if result is None:
        logger.info(f"[bold]Queued[/] request {request_id} from {user}")


def _reject(sdir: Path, file: Path, reason: str) -> None:
    logger.warning(f"Rejected {file.name}: {reason}")
    rejected = sdir / "rejected"
    try:
        os.replace(file, rejected / file.name)
    except FileNotFoundError:
        return
    (rejected / f"{file.name}.reason").write_text(reason + "\n")


def _owner(path: Path) -> str:
    uid = path.stat().st_uid
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)
