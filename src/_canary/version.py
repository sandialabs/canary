# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Runtime version resolution for the ``canary-wm`` distribution.

The published version is the plain, static ``version`` string in
``pyproject.toml`` (of the form ``YY.M.D``).  It is stamped by
``canary pre-commit`` and read back at runtime from the installed package
metadata.  This deliberately does *not* consult git at build time, so builds
from a ``.git``-stripped source tree (e.g. Spack) still report the correct
version.

Two contexts are handled:

* **Installed / non-editable (no reachable ``.git``)** -- e.g. a wheel or a
  Spack install.  ``version`` is exactly the metadata version.  No subprocess,
  no git, nothing that can fail if ``.git`` is absent.

* **Editable / source checkout (a ``.git`` is found above this module)** -- the
  metadata version is augmented with a local label ``+g<sha>[.dirty]`` so a
  developer's ``canary --version`` reflects the exact working state.  This
  string is intentionally *not* PEP 440 conformant; it is for human consumption
  on the command line only.

Module-level attributes ``version``, ``__version__``, ``version_info``, and
``__version_info__`` are resolved lazily via ``__getattr__``.
"""

import os
import re
import subprocess
from importlib import metadata as im

DIST_NAME = "canary-wm"


class GitRepoNotFoundError(Exception):
    pass


class CannotDetermineVersionFromGitError(Exception):
    pass


def _base_version() -> str:
    """The static, published version from installed package metadata."""
    try:
        return im.version(DIST_NAME)
    except im.PackageNotFoundError:
        # Not installed (e.g. running straight from a source tree that was
        # never `pip install`ed).  Fall back to reading pyproject.toml so that
        # `canary --version` still works during development.
        return _version_from_pyproject()


def _version_from_pyproject() -> str:
    root = _find_repo_root(os.path.dirname(__file__))
    if root is None:
        return "0.0.0"
    pyproject = os.path.join(root, "pyproject.toml")
    # Parse the static `version = "..."` line directly rather than importing a
    # TOML library: this fallback runs only for an uninstalled source tree, and
    # avoiding tomllib/tomli keeps it working on Python 3.10 with no extra deps.
    try:
        with open(pyproject, encoding="utf-8") as fh:
            in_project = False
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("["):
                    in_project = stripped.startswith("[project]")
                    continue
                if in_project:
                    m = re.match(r"""version\s*=\s*["'](?P<v>[^"']+)["']""", stripped)
                    if m:
                        return m.group("v")
    except OSError:
        pass
    return "0.0.0"


def _find_repo_root(start_dir: str) -> str | None:
    """Return the directory containing a ``.git`` at or above ``start_dir``."""
    d = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _git_toplevel(start_dir: str) -> str:
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
    return (
        subprocess.run(
            ["git", "-C", repo, "diff", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    )


def git_local_label() -> str:
    """``g<sha>[.dirty]`` for the repo containing this module.

    Raises if no git repo / git binary is available.
    """
    repo = _git_toplevel(os.path.dirname(__file__))
    sha = _git_short_sha(repo)
    local = f"g{sha}"
    if _git_is_dirty(repo):
        local += ".dirty"
    return local


def get_version() -> str:
    """Human-facing version string.

    Installed (no reachable ``.git``): the static metadata version.
    Source checkout (``.git`` present): metadata version + ``+g<sha>[.dirty]``.
    """
    base = _base_version()

    # Only augment for a real source checkout.  A wheel/Spack install has no
    # reachable .git, so this short-circuits before touching git at all.
    if _find_repo_root(os.path.dirname(__file__)) is None:
        return base

    # Don't stack a local segment on top of one already present.
    if "+" in base:
        return base

    try:
        return f"{base}+{git_local_label()}"
    except (GitRepoNotFoundError, CannotDetermineVersionFromGitError):
        return base


def get_version_info() -> tuple[int, int, int, str]:
    """Return ``(major, minor, micro, local)`` parsed from the version string.

    ``local`` is the segment after ``+`` (empty string if none).
    """
    v = get_version()
    if "+" in v:
        public, local = v.split("+", 1)
    else:
        public, local = v, ""

    parts = public.split(".")
    nums: list[int] = []
    for part in parts[:3]:
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)

    return nums[0], nums[1], nums[2], local


__version__: str
version: str
version_info: tuple[int, int, int, str]
__version_info__: tuple[int, int, int, str]


def __getattr__(name: str):
    if name in ("version", "__version__"):
        return get_version()
    if name in ("version_info", "__version_info__"):
        return get_version_info()
    raise AttributeError(name)
