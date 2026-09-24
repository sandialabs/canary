# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application-level orchestration for running (and re-running) a session.

This is the single place that turns a *run request* into an executed session:
open or create the workspace, resolve the request into a spec set, apply
selection filters, resolve the rerun strategy, and execute.  Interfaces (the
``run`` CLI subcommand today; a TUI/GUI later) build a :class:`RunOptions` plus
a request and call :func:`run`; they hold no orchestration logic of their own.

A *request* is any object exposing a ``kind`` string (``"scanpaths"``,
``"viewpaths"``, ``"specids"``, or ``"tag"``) and a ``value`` payload.  The
concrete request types live with the CLI parser, but this layer depends only on
that structural contract, not on the parser.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .. import rerun
from ..util import logging
from ..util.string import pluralize
from ..view import ViewSettings
from ..workspace import NotAWorkspaceError
from ..workspace import Workspace

logger = logging.get_logger(__name__)


@dataclass
class RunOptions:
    """Filters and execution settings for a :func:`run` call.

    These mirror the ``canary run`` options but carry no argparse coupling, so
    any interface can populate them.

    Attributes:
        tag: Name to give a new scanpaths selection (random if ``None``).
        on_options: ``-o`` build options used during collection.
        keyword_exprs: Keyword filter expressions.
        parameter_expr: Parameter filter expression.
        owners: Owner filter.
        regex: File-content regex filter.
        only: Explicit rerun strategy, or ``None`` to let :func:`run` choose the
            default appropriate to the request (``all`` for spec-id/view-path
            requests, ``not_pass`` otherwise).
        view: Result-view settings, or ``None`` to reuse the workspace default.
        wipe_workspace: Remove an existing workspace before running (only valid
            for scanpaths requests).
        work_tree: Root of the workspace; defaults to the current directory.
    """

    tag: str | None = None
    on_options: list[str] | None = None
    keyword_exprs: list[str] | None = None
    parameter_expr: str | None = None
    owners: list[str] | None = None
    regex: str | None = None
    only: str | None = None
    view: ViewSettings | None = None
    wipe_workspace: bool = False
    work_tree: str | None = None


def resolve_only(requested: str | None, kind: str) -> str:
    """Return the effective rerun strategy for a request of *kind*.

    An explicit strategy always wins.  Otherwise re-running specific tests by ID
    or view path defaults to ``all`` (run exactly what was named, even if it
    already passed); every other request defaults to ``not_pass``.  The ID/view
    default is logged so the choice is visible rather than silent.
    """
    if requested is not None:
        return requested
    if kind in ("specids", "viewpaths"):
        logger.info(
            "Re-running the requested tests with [bold]--only all[/] (pass --only to change)"
        )
        return "all"
    return "not_pass"


def _open_or_create_workspace(work_tree: str, wipe: bool, kind: str) -> Workspace:
    if wipe:
        if kind != "scanpaths":
            raise RuntimeError("Cannot remove existing workspace without additional scanpaths")
        Workspace.remove(work_tree)
    try:
        return Workspace.load(start=work_tree)
    except NotAWorkspaceError:
        return Workspace.create(path=work_tree)


def _resolve_specs(workspace: Workspace, kind: str, value: Any, options: RunOptions):
    """Resolve a request into the spec set to run, applying selection filters."""
    if kind == "scanpaths":
        return workspace.create_selection(
            tag=options.tag,
            scanpaths=value,
            on_options=options.on_options,
            keyword_exprs=options.keyword_exprs,
            parameter_expr=options.parameter_expr,
            owners=options.owners,
            regex=options.regex,
        )

    if kind == "specids":
        workspace.db.resolve_spec_ids(value)
        sids = [id[:7] for id in value]
        if len(sids) > 3:
            sids = [*sids[:2], "…", sids[-1]]
        logger.info(f"[bold]Running[/] {pluralize('spec', len(sids))} {', '.join(sids)}")
        specs = rerun.compute_rerun_closure(workspace.db, roots=value)
    elif kind == "viewpaths":
        logger.info("[bold]Running[/] tests from view paths")
        specs = rerun.get_specs_from_view(workspace.db, prefixes=value)
    elif kind == "tag":
        logger.info(f"[bold]Running[/] tests in tag {value}")
        specs = rerun.get_specs(workspace.db, tag=value)
    else:
        raise ValueError(f"Unknown run request kind: {kind!r}")

    workspace.apply_selection_rules(
        specs,
        keyword_exprs=options.keyword_exprs,
        parameter_expr=options.parameter_expr,
        owners=options.owners,
        regex=options.regex,
    )
    return specs


def run(request: Any, options: RunOptions | None = None) -> int:
    """Run (or re-run) the session described by *request* and return its exit code.

    Opens or creates the workspace at ``options.work_tree`` (current directory
    by default), resolves *request* into a spec set, applies selection filters,
    resolves the rerun strategy, executes the session, and returns its return
    code.

    Args:
        request: An object with ``kind`` and ``value`` attributes describing the
            tests to run (see the module docstring for the accepted kinds).
        options: Run filters and settings; defaults to :class:`RunOptions`.
    """
    options = options or RunOptions()
    kind = request.kind
    work_tree = options.work_tree or os.getcwd()

    workspace = _open_or_create_workspace(work_tree, options.wipe_workspace, kind)
    handler = logging.json_file_handler(workspace.logs_dir / "canary.0.log")
    logging.add_handler(handler)

    specs = _resolve_specs(workspace, kind, request.value, options)
    inplace = kind == "viewpaths"
    only = resolve_only(options.only, kind)
    session = workspace.run(specs, inplace=inplace, only=only, view_t=options.view)
    return session.returncode
