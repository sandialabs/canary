# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Subprocess helpers for running pytest in worker processes.

These are kept in the installed ``_canary`` package so that
:class:`concurrent.futures.ProcessPoolExecutor` workers can unpickle them
regardless of whether the ``dev/`` developer tree is on ``sys.path``.
"""

import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PytestResult:
    """Outcome of a single pytest worker invocation."""

    path: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float

    @property
    def ok(self) -> bool:
        """Return ``True`` if the pytest run exited with code 0."""
        return self.returncode == 0


def run_pytest_one(root: str, relpath: str, pytest_args: tuple[str, ...] = ()) -> PytestResult:
    """Run pytest on a single path in a worker process and return the result.

    Args:
        root: Absolute path to the repository root (used as ``cwd``).
        relpath: Relative path to the test directory/file to pass to pytest.
        pytest_args: Additional arguments forwarded to pytest.

    Returns:
        A :class:`PytestResult` capturing the return code, captured output,
        and elapsed time.
    """
    t0 = time.time()
    command = ["pytest", relpath, *pytest_args]
    cp = subprocess.run(
        command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8"
    )

    return PytestResult(
        path=relpath,
        returncode=cp.returncode,
        stdout=cp.stdout or "",
        stderr=cp.stderr or "",
        elapsed_s=time.time() - t0,
    )
