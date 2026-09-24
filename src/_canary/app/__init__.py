# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary application layer.

A single in-process entry point for opening a Canary :class:`~_canary.workspace.Workspace`
and observing application events, intended to be shared by every interface
(CLI, and future TUI/GUI/VS Code) so business logic lives here rather than in
any one interface.

This module is a facade: it delegates to the existing implementation
(:class:`~_canary.workspace.Workspace`) and adds no behavior of its own.
"""

from .facade import collect
from .facade import create_workspace
from .facade import get_event_bus
from .facade import open_workspace

__all__ = ["collect", "create_workspace", "open_workspace", "get_event_bus"]
