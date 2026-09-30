# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary terminal user interface (TUI).

An interactive, read-only explorer over the current workspace, built on
``rich`` (already a Canary dependency).  It is a thin interface *adapter*: all
data comes from the application query surface (:mod:`_canary.app.queries`) and
no business logic lives here, so the CLI, TUI, and future GUI/REST interfaces
all sit on the same ``canary.app`` layer.

Structure:

* :mod:`~_canary.tui.state` -- a pure, testable UI state machine.
* :mod:`~_canary.tui.render` -- pure Rich rendering of that state.
* :mod:`~_canary.tui.app` -- the runner that wires the application query
  surface to :class:`rich.live.Live` and the keyboard.
"""

from .app import ExplorerModel
from .app import run
from .state import ExplorerState

__all__ = ["run", "ExplorerModel", "ExplorerState"]
