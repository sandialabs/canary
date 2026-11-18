# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary application layer: the use cases every interface shares.

Interfaces (CLI, TUI, the Python API) turn user input into a request; the
functions here decide what that request means -- which specs to run, the rerun
strategy, which jobs to rebaseline, how to project results for display -- and
drive the :class:`~_canary.engine.engine.Engine` or read the
:class:`~_canary.workspace.workspace.Workspace`.  A function belongs here only
if it decides or combines something; plain reads go straight to ``Workspace``.
"""

from .exec_ import exec_job
from .pathspec import classify_pathspec
from .queries import JobView
from .queries import WorkspaceSummary
from .queries import job_history
from .queries import job_log
from .queries import list_jobs
from .queries import status_counts
from .queries import workspace_summary
from .rebaseline import rebaseline
from .run import RunOptions
from .run import run
from .run_subprocess import RunHandle
from .run_subprocess import run_in_subprocess
from .runhook import RunHookOptions
from .runhook import run_hook
from .selection import create_selection
from .selection import select

__all__ = [
    "run",
    "RunOptions",
    "run_hook",
    "RunHookOptions",
    "run_in_subprocess",
    "RunHandle",
    "rebaseline",
    "exec_job",
    "classify_pathspec",
    "select",
    "create_selection",
    "list_jobs",
    "job_history",
    "job_log",
    "workspace_summary",
    "status_counts",
    "JobView",
    "WorkspaceSummary",
]
