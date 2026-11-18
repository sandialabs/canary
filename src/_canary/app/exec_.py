# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application-level operation for executing a single job directly.

``canary exec`` runs one job by spec id, bypassing the session scheduler.  The
:class:`~_canary.engine.engine.Engine` builds the job (:meth:`Engine.job_for`) and
runs and records it (:meth:`Engine.exec_job`); the CLI subcommand only supplies
live-status rendering through an *observer*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..engine.engine import Engine
from ..engine.engine import JobEventObserver
from ..workspace.workspace import Workspace

if TYPE_CHECKING:
    from ..core.job import Job


def exec_job(
    spec_id: str, *, session: str | None = None, observer: JobEventObserver | None = None
) -> "Job":
    """Execute the single job identified by *spec_id* and return the run job.

    Opens the current workspace, builds the job with its upstream dependencies,
    runs it, and records the result (see :meth:`Engine.exec_job
    <_canary.engine.engine.Engine.exec_job>`).

    Args:
        spec_id: The spec id (or matching pattern) of the job to run.
        session: Name of the session directory to run in; defaults to a
            timestamped name so repeated ``exec`` runs do not collide.
        observer: Optional callback invoked with each executor event (the raw
            ``{"event", "timestamp"}`` dict plus the running ``Job`` under
            ``"job"``) as the job progresses, for live status rendering.

    Returns:
        The executed :class:`~_canary.core.job.Job`, carrying its final status
        (BLOCKED, without running, if an upstream outcome blocks it).

    Raises:
        RuntimeError: If an upstream dependency has not finished yet.
    """
    engine = Engine(Workspace.load())
    return engine.exec_job(engine.job_for(spec_id, session=session), observer=observer)
