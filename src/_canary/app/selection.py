# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Selection use case: save a filtered set of specs under a tag."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..engine.engine import Engine
from ..workspace.workspace import NotAWorkspaceError
from ..workspace.workspace import Workspace

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec


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
        ~_canary.workspace.workspace.NotAWorkspaceError: If no workspace exists.
    """
    engine = Engine(Workspace.load())
    filters: dict = dict(
        prefixes=prefixes,
        keyword_exprs=keyword_exprs,
        parameter_expr=parameter_expr,
        owners=owners,
        regex=regex,
    )
    if from_tag is not None:
        return engine.select_from_tag(tag, from_tag, **filters)
    return engine.select(tag, **filters)


def create_selection(
    tag: str | None,
    scanpaths: dict[str, list[str]],
    *,
    create_workspace: bool = False,
    on_options: list[str] | None = None,
    keyword_exprs: list[str] | None = None,
    parameter_expr: str | None = None,
    owners: list[str] | None = None,
    regex: str | None = None,
) -> list["JobSpec"]:
    """Collect *scanpaths* into the current workspace and save the filtered specs as *tag*.

    Args:
        tag: Selection name (random if ``None``).
        scanpaths: Paths to scan for generators.
        create_workspace: Create a workspace in the current directory if none exists.

    Raises:
        ~_canary.workspace.workspace.NotAWorkspaceError: If no workspace exists and
            *create_workspace* is false.
    """
    try:
        workspace = Workspace.load()
    except NotAWorkspaceError:
        if not create_workspace:
            raise
        workspace = Workspace.create()
    return Engine(workspace).create_selection(
        tag,
        scanpaths,
        on_options=on_options,
        keyword_exprs=keyword_exprs,
        parameter_expr=parameter_expr,
        owners=owners,
        regex=regex,
    )
