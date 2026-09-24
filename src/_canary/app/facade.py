# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Thin delegating facade over the workspace implementation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..events import EventBus
from ..workspace import Workspace

if TYPE_CHECKING:
    from ..jobspec import JobSpec

_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Return the process-wide application :class:`~_canary.events.EventBus`.

    The bus has no publishers wired to it yet; it is the subscription point
    future interfaces (and the execution layer) will use for live updates.
    """
    return _event_bus


def open_workspace(start: str | Path | None = None) -> Workspace:
    """Load the nearest existing workspace.

    Delegates to :meth:`Workspace.load`; see it for the resolution order and the
    :class:`~_canary.workspace.NotAWorkspaceError` raised when none is found.
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
    resolved :class:`~_canary.jobspec.JobSpec` objects.  Raises
    :class:`~_canary.workspace.NotAWorkspaceError` when no workspace exists.
    """
    return open_workspace().collect(scanpaths, on_options=on_options)
