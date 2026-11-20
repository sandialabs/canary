# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Record the git commit of each job's file as a measurement.

Enable with ``canary -p canary_git run ...``.  When a job's file is tracked by git, the job
gets a ``git`` measurement::

    {"commit": "<HEAD sha>", "dirty": <file differs from HEAD>, "root": "<repo>", "path": "<file>"}

Nothing is recorded when the file is not tracked, git is missing, or git fails.
"""

import os
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

import canary

logger = canary.get_logger(__name__)

#: Seconds to wait for each git command before giving up.
GIT_TIMEOUT = 10


@canary.hookimpl(trylast=True)
def canary_runteststart(case: "canary.Job") -> None:
    if info := git_info(Path(case.file)):
        case.add_measurement("git", info)


def git_info(file: Path) -> dict[str, Any] | None:
    """Return git provenance for ``file``, or ``None`` if it is not tracked by git."""
    file = file.absolute()
    try:
        root, commit = _git(file.parent, "rev-parse", "--show-toplevel", "HEAD").splitlines()
        path = _git(file.parent, "ls-files", "--full-name", "--error-unmatch", "--", file.name)
        status = _git(file.parent, "status", "--porcelain", "--", file.name)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        logger.debug(f"canary_git: no git info for {file}: {e}")
        return None
    return {"commit": commit, "dirty": bool(status), "root": root, "path": path}


def _git(cwd: Path, *args: str) -> str:
    # Many jobs run this at once, possibly while the user runs git in the same repo.  These
    # commands only read; GIT_OPTIONAL_LOCKS=0 stops ``git status`` from taking index.lock to
    # refresh the index, which could make the user's own git commands fail.
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    cp = subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=GIT_TIMEOUT
    )
    if cp.returncode != 0:
        raise subprocess.SubprocessError(cp.stderr.strip())
    return cp.stdout.strip()
