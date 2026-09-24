# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Application-level operation for executing a single job directly.

``canary exec`` runs one job by spec id, bypassing the session scheduler.  This
module owns that orchestration -- open the workspace, resolve the spec, build
the job graph, check readiness, run the job, and persist the result -- so the
CLI subcommand is a thin adapter that only supplies live-status rendering.

    Because there is no scheduler slot to advance the job's lifecycle, the job's
    phase transitions are driven here from the executor's event stream.  Callers
    that want to render live status pass an *observer*; it receives each event
    (with the :class:`~_canary.job.Job` added under the ``"job"`` key) after the
    phase transition has been applied.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from typing import Callable

from ..runtest import JobExecutor
from .facade import open_workspace

if TYPE_CHECKING:
    from ..job import Job

#: An observer receives each raw executor event dict as it occurs.
JobEventObserver = Callable[[dict], None]


def exec_job(
    spec_id: str, *, session: str | None = None, observer: JobEventObserver | None = None
) -> "Job":
    """Execute the single job identified by *spec_id* and return the run job.

    Opens the current workspace, resolves *spec_id* (id or matching pattern),
    constructs the job together with its upstream dependencies, runs it if it is
    ready, and persists the result.

    Args:
        spec_id: The spec id (or matching pattern) of the job to run.
        session: Name of the session directory to run in; defaults to a
            timestamped name so repeated ``exec`` runs do not collide.
        observer: Optional callback invoked with each executor event (the raw
            ``{"event", "timestamp"}`` dict plus the running ``Job`` under
            ``"job"``) as the job progresses, for live status rendering.

    Returns:
        The executed :class:`~_canary.job.Job`, carrying its final status.

    Raises:
        RuntimeError: If the resolved job is not ready to run (e.g. an upstream
            dependency has not completed).
    """
    workspace = open_workspace()
    session_name = session or _default_session_name()
    session_dir = workspace.sessions_dir / session_name

    spec = workspace.find_jobspec(spec_id)
    specs = workspace.db.load_specs(ids=[spec.id], include_upstreams=True)
    jobs = workspace.construct_jobs(specs, session_dir)
    job: Job = next(j for j in jobs if j.id == spec.id)

    job.status.reset()
    job.state.reset()
    if not job.is_ready():
        raise RuntimeError(f"{job}: job is not ready to run")

    JobExecutor()(job, _PhaseTrackingSink(job, observer))
    workspace.db.put_results(job)
    return job


def _default_session_name() -> str:
    """Return a filesystem-safe, timestamped session name."""
    now = datetime.datetime.now()
    return now.isoformat(timespec="microseconds").replace(":", "-")


class _PhaseTrackingSink:
    """Advance a job's lifecycle from executor events, forwarding each to an observer.

    :class:`~_canary.runtest.JobExecutor` drives a job by ``put``-ing event
    dicts onto a queue-like sink.  In the session scheduler that sink advances
    the job's phase via an :class:`ExecutionSlot`; ``exec`` has no slot, so this
    sink applies the same ``on_submit``/``on_stage``/``on_start``/``on_stop``
    transitions.  Each event is then forwarded to the caller's *observer* (if
    any), with the running job added under ``"job"``, so the observer can render
    without owning the transition logic or needing a separate job reference.
    """

    def __init__(self, job: "Job", observer: JobEventObserver | None) -> None:
        self._job = job
        self._observer = observer

    def put(self, event: dict) -> None:
        name = event.get("event")
        at = event.get("timestamp")
        if name == "job_submitted":
            self._job.on_submit(at=at)
        elif name == "job_staged":
            self._job.on_stage(at=at)
        elif name == "job_started":
            self._job.on_start(at=at)
        elif name == "job_stopped":
            self._job.on_stop(at=at)
        if self._observer is not None:
            self._observer({**event, "job": self._job})
