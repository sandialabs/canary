# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Thin delegating facade over the workspace implementation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..events import EventBus
from ..session.workspace import Workspace

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec

_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Return the process-wide application :class:`~_canary.events.EventBus`.

    During an in-process run the executor publishes job-lifecycle events here
    (see :meth:`ResourceQueueExecutor.notify_listeners`), each carrying a
    primitives-only :class:`~_canary.events.JobEvent` payload.  Interfaces (the
    TUI today; a future GUI/REST bridge) subscribe to observe live progress.
    Cross-process delivery -- when the observing interface is a separate process
    from the run -- is out of scope for this in-process bus and belongs to a
    future transport.
    """
    return _event_bus


def open_workspace(start: str | Path | None = None) -> Workspace:
    """Load the nearest existing workspace.

    Delegates to :meth:`Workspace.load`; see it for the resolution order and the
    :class:`~_canary.session.workspace.NotAWorkspaceError` raised when none is found.
    """
    return Workspace.load(start)


def create_workspace(path: str | Path = Path.cwd(), force: bool = False) -> Workspace:
    """Create a new workspace at *path*.

    Delegates to :meth:`Workspace.create`.
    """
    return Workspace.create(path, force=force)


def collect(
    scanpaths: dict[str, list[str]], on_options: list[str] | None = None
) -> list["JobSpec"]:
    """Discover test generators under *scanpaths* and store the resolved specs.

    Opens the nearest existing workspace, runs collection, and returns the
    resolved :class:`~_canary.core.jobspec.JobSpec` objects.  Raises
    :class:`~_canary.session.workspace.NotAWorkspaceError` when no workspace exists.
    """
    return open_workspace().collect(scanpaths, on_options=on_options)


def delete_selection(tag: str) -> None:
    """Delete the named selection *tag* from the current workspace."""
    open_workspace().db.delete_selection(tag)


def is_selection(tag: str) -> bool:
    """Return ``True`` if *tag* names an existing selection in the current workspace."""
    return open_workspace().is_tag(tag)


def rename_selection(old: str, new: str) -> None:
    """Rename selection *old* to *new* in the current workspace."""
    open_workspace().db.rename_selection(old, new)


def select(
    tag: str,
    *,
    from_tag: str | None = None,
    prefixes: list[str] | None = None,
    keyword_exprs: list[str] | None = None,
    parameter_expr: str | None = None,
    owners: list[str] | None = None,
    regex: str | None = None,
) -> list["JobSpec"]:
    """Create a named selection *tag* from filtered specs.

    Draws candidate specs from every spec in the workspace, or from the specs of
    *from_tag* when given, applies the filters, stores the result under *tag*,
    and returns the selected specs.  Callers that must reject an existing *tag*
    should check :func:`is_selection` first.

    Raises:
        ~_canary.session.workspace.NotAWorkspaceError: If no workspace exists.
    """
    workspace = open_workspace()
    filters: dict = dict(
        prefixes=prefixes,
        keyword_exprs=keyword_exprs,
        parameter_expr=parameter_expr,
        owners=owners,
        regex=regex,
    )
    if from_tag is not None:
        return workspace.select_from_tag(tag, from_tag, **filters)
    return workspace.select(tag, **filters)


def get_workspace_info() -> dict:
    """Return summary information about the current workspace.

    Delegates to :meth:`Workspace.info`; see it for the returned keys.
    """
    return open_workspace().info()


def get_tag_info(tag: str) -> dict:
    """Return metadata and unmasked specs for selection *tag*.

    Delegates to :meth:`Workspace.tag_info`.  Raises
    :class:`~_canary.persistence.database.NotASelection` if *tag* is not a selection.
    """
    return open_workspace().tag_info(tag)


def get_results(ids: list[str] | None = None, include_upstreams: bool = False) -> dict[str, dict]:
    """Return the latest result record for each spec in the current workspace.

    Delegates to :meth:`WorkspaceDatabase.get_results`; see it for the returned
    mapping and the meaning of *ids*/*include_upstreams*.
    """
    return open_workspace().db.get_results(ids, include_upstreams=include_upstreams)


def get_result_history(spec_id: str) -> list:
    """Return all historical result records for *spec_id*, oldest first.

    Delegates to :meth:`WorkspaceDatabase.get_result_history`.
    """
    return open_workspace().db.get_result_history(spec_id)
