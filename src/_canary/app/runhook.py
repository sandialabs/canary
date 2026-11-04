# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Replay selected per-job hooks against stored Canary results."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .. import config
from ..core.rules import RerunRule
from ..select import RuntimeSelector
from ..session.workspace import Workspace
from ..util import logging
from .facade import open_workspace
from .query_helpers import resolve_session_dir
from .rebaseline import _jobs_from_result_rows
from .rebaseline import filter_jobs_by_keywords

logger = logging.get_logger(__name__)


@dataclass
class RunHookOptions:
    keyword_exprs: list[str] | None = None
    only: str | None = None
    session: str = "latest"
    work_tree: str | None = None


def run_hook(hook_name: str, request: Any, options: RunHookOptions | None = None) -> int:
    options = options or RunHookOptions()
    if hook_name != "canary_runtest_finish":
        raise ValueError(f"Unsupported runhook hook: {hook_name!r}")

    workspace = open_workspace(start=options.work_tree)
    jobs = _resolve_hook_jobs(workspace, request, options)
    if not jobs:
        logger.warning(f"No jobs selected for {hook_name}")
        return 0

    failures = 0
    for job in jobs:
        logger.info(
            f"[bold]Running hook[/] {hook_name} on {job.display_name(style='rich', resolve=True)}"
        )
        try:
            with job.workspace.enter():
                config.pluginmanager.hook.canary_runtest_finish(case=job)
            job.save()
        except Exception:
            failures += 1
            logger.exception("%s failed for %s", hook_name, job.id[:7])

    logger.info(f"[bold]Ran hook[/] {hook_name} for {len(jobs)} job(s)")
    return failures


def _resolve_hook_jobs(workspace: Workspace, request: Any, options: RunHookOptions) -> list[Any]:
    rows = _result_rows_for_request(workspace, request, session=options.session)
    jobs = _jobs_from_result_rows(workspace, rows)
    saved = {
        job.id: (
            copy.deepcopy(job.status),
            copy.deepcopy(job.timekeeper),
            copy.deepcopy(job.measurements),
            copy.deepcopy(job.state),
        )
        for job in jobs
    }
    selector = RuntimeSelector(jobs, workspace=workspace.root)
    selector.add_rule(RerunRule(strategy=options.only or "all"))
    selector.run()
    for job in jobs:
        job.status, job.timekeeper, job.measurements, job.state = saved[job.id]
    selected = [job for job in jobs if not job.mask]
    return filter_jobs_by_keywords(selected, options.keyword_exprs)


def _result_rows_for_request(
    workspace: Workspace, request: Any, *, session: str
) -> list[dict[str, Any]]:
    if request.kind == "tag":
        tag = request.value
        if tag == config.get("run:default_tag"):
            session_dir = resolve_session_dir(workspace, session)
            return workspace.db.get_results_for_session(session_dir.name)
        ids = [spec.id for spec in workspace.db.load_specs_by_tagname(tag)]
        result_map = workspace.db.get_results(ids)
        return [result_map[spec_id] for spec_id in ids if spec_id in result_map]
    if request.kind == "specids":
        result_map = workspace.db.get_results(list(request.value))
        return list(result_map.values())
    if request.kind == "viewpaths":
        ids = workspace.db.select_from_view(list(request.value))
        result_map = workspace.db.get_results(ids)
        return [result_map[spec_id] for spec_id in ids if spec_id in result_map]
    raise ValueError(f"Unsupported runhook request kind: {request.kind!r}")
