# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application-level rebaseline operation.

Resolve the jobs implied by one or more targets (results directories or job
ids/names), optionally filter them by keyword, and invoke the
``canary_runtest_rebaseline`` hook for each.  The ``rebaseline``
CLI subcommand is a thin adapter over :func:`rebaseline`.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from .. import config
from ..core.rules import KeywordRule
from ..execution.testexec import ExecutionSpace
from ..session.workspace import Workspace
from ..util import logging
from .facade import open_workspace

if TYPE_CHECKING:
    from ..core.job import Job

logger = logging.get_logger(__name__)


def rebaseline(target: str | Sequence[str] = ".", keyword_exprs: list[str] | None = None) -> int:
    """Rebaseline the jobs selected by *target*, filtered by *keyword_exprs*.

    Opens the current workspace, resolves every target into jobs, applies the
    keyword filter, and runs the ``canary_runtest_rebaseline`` hook for each
    selected job.  All targets are resolved before any baseline is touched, so
    an unresolvable target aborts the operation without partial updates.  A job
    selected by more than one target is rebaselined once.

    Args:
        target: A results directory (or ``testcase.lock`` file) or a job
            id/name, or a sequence of them.  An empty sequence selects nothing.
        keyword_exprs: Optional keyword expressions restricting which jobs are
            rebaselined.

    Returns:
        The number of jobs rebaselined.
    """
    targets = [target] if isinstance(target, str) else list(target)
    if not targets:
        # An explicitly empty selection means "nothing", never "everything".
        logger.warning("No jobs selected for rebaseline")
        return 0
    workspace = open_workspace()
    jobs = resolve_rebaseline_targets(workspace, targets, keyword_exprs=keyword_exprs)

    if not jobs:
        logger.warning("No jobs selected for rebaseline")
        return 0

    for job in jobs:
        logger.info(f"[bold]Rebaselining[/] {job.display_name(style='rich', resolve=True)}")
        config.pluginmanager.hook.canary_runtest_rebaseline(case=job)

    logger.info(f"[bold]Rebaselined[/] {len(jobs)} job(s)")
    return len(jobs)


def resolve_rebaseline_targets(
    workspace: Workspace, targets: Sequence[str], keyword_exprs: list[str] | None = None
) -> list["Job"]:
    """Resolve every target in *targets* and return the de-duplicated union of jobs.

    Order follows *targets* (then each target's own ordering).  Two selections
    are duplicates when they name the same job *and* the same results
    directory, so naming a job twice (e.g. by id and by name) rebaselines it
    once, while explicitly selecting results from two sessions keeps both.
    """
    seen: set[tuple[str, str | None]] = set()
    jobs: list[Job] = []
    for target in targets:
        for job in resolve_rebaseline_jobs(workspace, target, keyword_exprs=keyword_exprs):
            space = getattr(job, "workspace", None)
            key = (job.id, str(space.dir) if space is not None else None)
            if key in seen:
                continue
            seen.add(key)
            jobs.append(job)
    return jobs


def resolve_rebaseline_jobs(
    workspace: Workspace, target: str, keyword_exprs: list[str] | None = None
) -> list["Job"]:
    """Return the jobs implied by *target* (a results path or a job id/name)."""
    path = Path(target)
    if path.exists():
        return jobs_from_path(workspace, path, keyword_exprs=keyword_exprs)
    jobs = [workspace.find(job=target)]
    return filter_jobs_by_keywords(jobs, keyword_exprs)


def jobs_from_path(
    workspace: Workspace, path: Path, keyword_exprs: list[str] | None = None
) -> list["Job"]:
    """Resolve *path* to jobs using workspace metadata before materializing Job objects."""
    job_ids, rows = _select_rebaseline_jobs_from_path(workspace, path)
    if rows is not None:
        rows = _filter_result_rows_by_keywords(workspace, rows, keyword_exprs)
        return _jobs_from_result_rows(workspace, rows)

    job_ids = _filter_job_ids_by_keywords(workspace, job_ids, keyword_exprs)
    return workspace.load_jobs(job_ids)


def _select_rebaseline_jobs_from_path(
    workspace: Workspace, path: Path
) -> tuple[list[str], list[dict[str, Any]] | None]:
    """Return either latest-result spec ids or exact historical result rows for *path*."""
    resolved = path.absolute()

    if resolved.is_file():
        if resolved.name != "testcase.lock":
            raise ValueError(f"{resolved}: expected testcase.lock")
        resolved = resolved.parent

    if not resolved.is_dir():
        raise ValueError(f"{resolved}: no such file or directory")

    if rel_view := workspace.relative_to_view(resolved):
        prefix = rel_view if resolved.is_file() else rel_view.rstrip("/") + "/%"
        return workspace.db.select_from_view([prefix]), None

    if workspace.is_session_dir(resolved):
        return [], _select_rebaseline_result_rows_from_session_path(workspace, resolved)

    if resolved == workspace.root.absolute():
        return list(workspace.db.get_results().keys()), None

    return _select_rebaseline_job_ids_from_source_path(workspace, resolved), None


def _select_rebaseline_result_rows_from_session_path(
    workspace: Workspace, path: Path
) -> list[dict[str, Any]]:
    rel = path.absolute().relative_to(workspace.sessions_dir)
    session = rel.parts[0]
    session_root = workspace.sessions_dir / session
    rows = workspace.db.get_results_for_session(session)
    if len(rel.parts) == 1:
        return rows

    selected: list[dict[str, Any]] = []
    for row in rows:
        job_dir = (session_root / row["workspace"]).resolve()
        if job_dir == path or job_dir.is_relative_to(path) or path.is_relative_to(job_dir):
            selected.append(row)
    return selected


def _select_rebaseline_job_ids_from_source_path(workspace: Workspace, path: Path) -> list[str]:
    candidates = workspace.db.get_partial_specs()
    selected: list[str] = []
    for spec in candidates:
        source = spec.file.resolve()
        if source == path or source.is_relative_to(path):
            selected.append(spec.id)
    return selected


def _filter_job_ids_by_keywords(
    workspace: Workspace, job_ids: list[str], keyword_exprs: list[str] | None
) -> list[str]:
    if not keyword_exprs or not job_ids:
        return job_ids
    specs = workspace.db.load_specs(job_ids)
    rule = KeywordRule(keyword_exprs)
    return [spec.id for spec in specs if rule(spec)]


def _filter_result_rows_by_keywords(
    workspace: Workspace, rows: list[dict[str, Any]], keyword_exprs: list[str] | None
) -> list[dict[str, Any]]:
    if not keyword_exprs or not rows:
        return rows
    selected_ids = set(
        _filter_job_ids_by_keywords(workspace, [row["id"] for row in rows], keyword_exprs)
    )
    return [row for row in rows if row["id"] in selected_ids]


def _jobs_from_result_rows(workspace: Workspace, rows: list[dict[str, Any]]) -> list["Job"]:
    if not rows:
        return []
    specs = workspace.db.load_specs([row["id"] for row in rows])
    spec_map = {spec.id: spec for spec in specs}
    jobs: list[Job] = []
    for row in rows:
        spec = spec_map[row["id"]]
        space = ExecutionSpace(
            root=workspace.sessions_dir / row["session"],
            path=Path(row["workspace"]),
            session=row["session"],
        )
        from ..core.job import Job

        job = Job(spec=spec, workspace=space)
        job.status = row["status"]
        job.timekeeper = row["timekeeper"]
        job.measurements = row["measurements"]
        job.state = row["state"]
        if space.joinpath("testcase.lock").exists():
            job.refresh()
        jobs.append(job)
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
