# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Version resolution for the ``canary-wm`` distribution.

For installed (non-editable) packages the version is read directly from
package metadata via ``importlib.metadata``.

For editable (development) installs the metadata version is used as the base,
and a ``+g<sha>[.dirty]`` local segment is appended by querying the git
repository at the package source location.

Module-level attributes ``__version__``, ``version``, ``version_info``, and
``__version_info__`` are resolved lazily via ``__getattr__`` to avoid running
subprocess calls at import time.
"""

import json
import os
import subprocess
from importlib import metadata as im

DIST_NAME = "canary-wm"


class GitRepoNotFoundError(Exception):
    """Raised when the package source directory is not inside a git repository."""

    pass


class CannotDetermineVersionFromGitError(Exception):
    """Raised when git is available but the version cannot be determined (e.g. no commits)."""

    pass


def is_editable(dist_name: str = DIST_NAME) -> bool:
    """
    Best-effort PEP 610 editable detection via direct_url.json.
    Returns False if unavailable.
    """
    try:
        dist = im.distribution(dist_name)
    except im.PackageNotFoundError:
        return False

    try:
        direct_url_content = dist.read_text("direct_url.json")
    except Exception:
        direct_url_content = None

    if not direct_url_content:
        return False

    try:
        data = json.loads(direct_url_content)
    except json.JSONDecodeError:
        return False

    return bool(data.get("dir_info", {}).get("editable", False))


def _git_toplevel(start_dir: str) -> str:
    """Return the absolute path of the git repository root for *start_dir*.

    Raises:
        GitRepoNotFoundError: If *start_dir* is not inside a git repository.
    """
    proc = subprocess.run(
        ["git", "-C", start_dir, "rev-parse", "--show-toplevel"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise GitRepoNotFoundError(start_dir)
    return proc.stdout.strip()


def _git_short_sha(repo: str) -> str:
    """Return the short (7-char) SHA of HEAD in *repo*.

    Raises:
        CannotDetermineVersionFromGitError: If ``git rev-parse`` fails.
    """
    proc = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--short", "HEAD"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise CannotDetermineVersionFromGitError("git rev-parse failed")
    return proc.stdout.strip()


def _git_is_dirty(repo: str) -> bool:
    """Return ``True`` if the working tree in *repo* has uncommitted changes."""
    return (
        subprocess.run(
            ["git", "-C", repo, "diff", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    )


def git_local_label() -> str:
    """Return a PEP 440 local segment string for the current git state.

    Returns strings like ``'g3a1b2c3'`` (clean) or ``'g3a1b2c3.dirty'``
    (uncommitted changes present).

    Raises:
        GitRepoNotFoundError: If the package source is not in a git repo.
        CannotDetermineVersionFromGitError: If the SHA cannot be determined.
    """
    repo = _git_toplevel(os.path.dirname(__file__))
    sha = _git_short_sha(repo)
    local = f"g{sha}"
    if _git_is_dirty(repo):
        local += ".dirty"
    return local


def _parse_dist_version(v: str) -> tuple[int, int, int, str]:
    """
    Parses enough PEP 440 to support:
      - X.Y.Z
      - X.Y.Z.devN
      - X.Y.Z.<anything> (we ignore beyond Z for numeric triplet)
      - optional +local
    Returns (major, minor, micro, local) where local excludes '+'.
    """
    if "+" in v:
        public, local = v.split("+", 1)
    else:
        public, local = v, ""

    # numeric release triplet from the start of public part
    parts = public.split(".")
    if len(parts) < 3:
        raise ValueError(f"Expected at least three numeric components, got {v!r}")

    major = int(parts[0])
    minor = int(parts[1])

    micro_str = parts[2]
    micro_digits = ""
    for ch in micro_str:
        if ch.isdigit():
            micro_digits += ch
        else:
            break
    micro = int(micro_digits) if micro_digits else 0

    return major, minor, micro, local


def get_version_info() -> tuple[int, int, int, str]:
    """
    For non-editable installs: returns metadata version triplet and local (if any).
    For editable installs: uses metadata triplet, but local becomes 'g<sha>[.dirty]'.
    """
    base = im.version(DIST_NAME)
    major, minor, micro, local = _parse_dist_version(base)

    if is_editable(DIST_NAME):
        # If base already has a local segment, keep it (avoid stacking).
        if not local:
            try:
                local = git_local_label()
            except (GitRepoNotFoundError, CannotDetermineVersionFromGitError):
                pass

    return major, minor, micro, local


def get_version() -> str:
    """Return the canonical version string for the ``canary-wm`` distribution.

    For non-editable installs this is the raw metadata version string.
    For editable installs a ``+g<sha>[.dirty]`` local segment is appended
    unless the metadata already contains a local segment.
    """
    major, minor, micro, local = get_version_info()
    v = f"{major}.{minor}.{micro}"

    # Preserve pre/dev info from metadata in the string if you want it:
    # We intentionally do NOT reconstruct '.devN' etc here; instead, return the
    # actual metadata version unless we need to append a local label.
    base = im.version(DIST_NAME)
    if not is_editable(DIST_NAME):
        return base

    # Editable: append local label only if base doesn't already have one
    if "+" in base:
        return base

    # If base already contains something like '.dev0', keep it, and add +local
    if local:
        return f"{base}+{local}" if "+" not in base else base
    return base


__version__: str
version: str
version_info: tuple[int, int, int, str]
__version_info__: tuple[int, int, int, str]


def __getattr__(name: str):
    """Lazily resolve ``__version__``, ``version``, ``version_info``, and ``__version_info__``."""
    if name in ("version", "__version__"):
        return get_version()
    if name in ("version_info", "__version_info__"):
        return get_version_info()
    raise AttributeError(name)
