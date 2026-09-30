# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application-level rebaseline operation.

Resolve the jobs implied by a target (a results directory containing
``testcase.lock`` files, or a job id/name), optionally filter them by keyword,
and invoke the ``canary_runtest_rebaseline`` hook for each.  The ``rebaseline``
CLI subcommand is a thin adapter over :func:`rebaseline`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .. import config
from ..core.rules import KeywordRule
from ..session.workspace import Workspace
from ..util import json_helper as json
from ..util import logging
from .facade import open_workspace

if TYPE_CHECKING:
    from ..core.job import Job

logger = logging.get_logger(__name__)


def rebaseline(target: str = ".", keyword_exprs: list[str] | None = None) -> int:
    """Rebaseline the jobs selected by *target*, filtered by *keyword_exprs*.

    Opens the current workspace, resolves *target* into jobs, applies the
    keyword filter, and runs the ``canary_runtest_rebaseline`` hook for each
    selected job.

    Args:
        target: A results directory (``testcase.lock`` files are found
            recursively) or a job id/name.
        keyword_exprs: Optional keyword expressions restricting which jobs are
            rebaselined.

    Returns:
        The number of jobs rebaselined.
    """
    workspace = open_workspace()
    jobs = resolve_rebaseline_jobs(workspace, target)
    jobs = filter_jobs_by_keywords(jobs, keyword_exprs)

    if not jobs:
        logger.warning("No jobs selected for rebaseline")
        return 0

    for job in jobs:
        logger.info(f"[bold]Rebaselining[/] {job.display_name(style='rich', resolve=True)}")
        config.pluginmanager.hook.canary_runtest_rebaseline(case=job)

    logger.info(f"[bold]Rebaselined[/] {len(jobs)} job(s)")
    return len(jobs)


def resolve_rebaseline_jobs(workspace: Workspace, target: str) -> list["Job"]:
    """Return the jobs implied by *target* (a results path or a job id/name)."""
    path = Path(target)
    if path.exists():
        return jobs_from_path(workspace, path)
    return [workspace.find(job=target)]


def jobs_from_path(workspace: Workspace, path: Path) -> list["Job"]:
    """Return the jobs for every unique ``testcase.lock`` found under *path*."""
    jobs: list["Job"] = []
    seen: set[str] = set()
    for lockfile in iter_lockfiles(path):
        lock_data = json.loads(lockfile.read_text())
        job_id = lock_data.spec.id
        if job_id in seen:
            continue
        seen.add(job_id)
        jobs.append(workspace.find(job=job_id))
    return jobs


def iter_lockfiles(path: Path):
    """Yield ``testcase.lock`` paths at or under *path*.

    Raises:
        ValueError: If *path* is a non-lock file or does not exist.
    """
    if path.is_file():
        if path.name != "testcase.lock":
            raise ValueError(f"{path}: expected testcase.lock")
        yield path
        return

    if not path.is_dir():
        raise ValueError(f"{path}: no such file or directory")

    for root, _dirs, files in os.walk(path, followlinks=True):
        if "testcase.lock" in files:
            yield Path(root) / "testcase.lock"


def filter_jobs_by_keywords(jobs: list["Job"], keyword_exprs: list[str] | None) -> list["Job"]:
    """Return the subset of *jobs* whose spec matches all *keyword_exprs*."""
    if not keyword_exprs:
        return jobs
    rule = KeywordRule(keyword_exprs)
    return [job for job in jobs if rule(job.spec)]
