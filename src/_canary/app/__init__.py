# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary application layer.

A single in-process entry point for opening a Canary :class:`~_canary.session.workspace.Workspace`
and observing application events, intended to be shared by every interface
(CLI, and future TUI/GUI/VS Code) so business logic lives here rather than in
any one interface.

This module is a facade: it delegates to the existing implementation
(:class:`~_canary.session.workspace.Workspace`) and adds no behavior of its own.
"""

from .exec_ import exec_job
from .facade import collect
from .facade import create_workspace
from .facade import delete_selection
from .facade import get_event_bus
from .facade import get_result_history
from .facade import get_results
from .facade import get_tag_info
from .facade import get_workspace_info
from .facade import is_selection
from .facade import open_workspace
from .facade import rename_selection
from .facade import select
from .pathspec import classify_pathspec
from .rebaseline import rebaseline
from .run import RunOptions
from .run import run

__all__ = [
    "collect",
    "create_workspace",
    "open_workspace",
    "get_event_bus",
    "run",
    "RunOptions",
    "rebaseline",
    "exec_job",
    "classify_pathspec",
    "select",
    "delete_selection",
    "rename_selection",
    "is_selection",
    "get_workspace_info",
    "get_tag_info",
    "get_results",
    "get_result_history",
]
