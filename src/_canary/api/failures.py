# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Any

from _canary.app.failure_analysis import collect_failure_groups
from _canary.cli import query as _query_cmd
from _canary.session.workspace import Workspace


def failures(
    *,
    session: str = "latest",
    where: str | None = None,
    group_by: str = "signature",
    frame_filter: str | None = None,
    include_pass_with_errors: bool = False,
    log_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    workspace = Workspace.load()
    session_dir = _query_cmd._resolve_session_dir(workspace, session)
    rows = _query_cmd._db_results_for_session(workspace, session_dir.name)
    predicate = _query_cmd._parse_where(where) if where else None
    if predicate is not None:
        rows = [row for row in rows if predicate(_query_cmd._row_to_job_entry(workspace, row))]
    return collect_failure_groups(
        workspace,
        rows,
        group_by=group_by,
        frame_filter=frame_filter,
        include_pass_with_errors=include_pass_with_errors,
        log_names=log_names,
    )


__all__ = ["failures"]
