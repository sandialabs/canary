# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Which filesystem trees a request may reach, and how the API shows paths in them.

A request may name paths inside the workspace (the directory holding ``.canary``) and
under the roots the operator lists in ``server:allowed_roots`` (a mapping of names to
paths; relative ones are relative to the workspace)::

    server:
      allowed_roots:
        src: /projects/app/src      # tests beside a scratch workspace

Anything else is refused (``403``).  In results the API shows the absolute paths of a job
record (``file_root``, ``exec_dir``) relative to the workspace when in it, as
``name:relative/path`` under an allowed root, and otherwise only by their last component
(``…/name``), so no server path is published that a caller did not name.  The relative
ones (``file_path``, relative to ``file_root``, the session and the view; ``exec_path``,
relative to the session) are canary's own and published as they are.
"""

import os
from pathlib import Path
from typing import Any
from typing import Iterable

from .. import config
from .dispatch import Context
from .dispatch import RequestError

#: The version-control forms of a scan root (``git@path``, ``repo@path``).
VC_PREFIXES = ("git@", "repo@")


def allowed_roots(ctx: Context) -> list[tuple[str | None, str]]:
    """``(name, real path)`` of the workspace (no name) and each ``server:allowed_roots``."""
    anchor = os.path.realpath(ctx.anchor)
    roots: list[tuple[str | None, str]] = [(None, anchor)]
    for name, path in (config.get("server:allowed_roots") or {}).items():
        roots.append((name, os.path.realpath(os.path.join(anchor, os.path.expanduser(path)))))
    return roots


def _under(real: str, root: str) -> bool:
    return real == root or real.startswith(root.rstrip(os.sep) + os.sep)


def check_paths(paths: Iterable[str], ctx: Context) -> None:
    """Refuse (``403``) a request that names a path outside the workspace and allowed roots.

    Relative *paths* are relative to the current directory (the worker runs in the
    request's cwd); symbolic links are resolved.
    """
    roots = allowed_roots(ctx)
    for path in paths:
        real = os.path.realpath(path)
        if not any(_under(real, root) for _, root in roots):
            names = ", ".join(name for name, _ in roots if name) or "none"
            raise RequestError(
                403,
                f"{path}: outside the workspace and the server's allowed roots ({names}); "
                "an operator can add it to server:allowed_roots",
            )


def scanned_paths(scanpaths: dict[str, list[str]]) -> list[str]:
    """Every path a scan reaches: each root, and each file listed under it."""
    out: list[str] = []
    for root, files in scanpaths.items():
        if root.startswith(VC_PREFIXES):
            root = root.partition("@")[2]
        out.append(root)
        out.extend(os.path.join(root, f) for f in files)
    return out


def public_path(path: str | None, ctx: Context) -> str | None:
    """*path* as the API shows it (see the module's docstring)."""
    if not path or not os.path.isabs(path):
        return path  # already relative to the workspace (or empty)
    real = os.path.realpath(path)
    for name, root in allowed_roots(ctx):
        if _under(real, root):
            rel = os.path.relpath(real, root)
            return rel if name is None else f"{name}:{rel}"
    return f"…/{Path(path).name}"


def publish(records: Any, ctx: Context) -> Any:
    """*records* (one job record or a list) with ``file_root``/``exec_dir`` made public."""
    if isinstance(records, list):
        return [publish(r, ctx) for r in records]
    if isinstance(records, dict) and "file_root" in records:
        return {
            **records,
            "file_root": public_path(records.get("file_root"), ctx),
            "exec_dir": public_path(records.get("exec_dir"), ctx),
        }
    return records
