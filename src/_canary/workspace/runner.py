# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Session preparation and execution.

:class:`SessionRunner` splits running a session into two phases:

* :meth:`SessionRunner.prepare` -- specs -> Jobs, runtime selection, session-directory
  retargeting, and the :class:`~_canary.workspace.session.Session` manifest.
* :meth:`SessionRunner.execute` -- result listener, live view, the run itself, and
  finalization (persist final state, reconcile, hooks, ``refs/latest``).

``Workspace.run()`` is ``execute(prepare(...))``.
"""

import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .. import config
from .. import select
from ..core import rules
from ..core.job import Job
from ..persistence.listener import ResultListener
from ..util import logging
from ..util.filesystem import atomic_write
from ..view import ViewManager
from ..view import ViewSettings
from .reconstruction import JobReconstructor
from .session import Session

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..execution.queue_executor import ExecutionEvent
    from .workspace import Workspace

logger = logging.get_logger(__name__)

_SESSION_DIR_VARIABLES = ("PYTHONPATH", "PATH")


class SessionRunner:
    """Prepare and execute test sessions for a :class:`Workspace`."""

    def __init__(self, workspace: "Workspace", reconstructor: JobReconstructor) -> None:
        self.workspace = workspace
        self.reconstructor = reconstructor

    def prepare(
        self,
        specs: list["JobSpec"],
        *,
        session: str | None = None,
        inplace: bool = False,
        only: str = "not_pass",
    ) -> Session:
        """Build the jobs for *specs* and return a Session ready for :meth:`execute`.

        Nothing is executed and no listener or view is started.  For a new session in
        the parent process, ``canary_sessionstart`` fires and ``session.lock`` is written.

        Args:
            specs: Job specs to run.
            session: Name of an existing session to reuse.
            inplace: If True, run jobs in their existing result directories.
            only: Rerun strategy (e.g. ``'not_pass'``).

        Raises:
            ValueError: If *session* is given but does not exist.
            RuntimeError: If *inplace* is requested but a job's results do not exist.
        """
        ws = self.workspace
        reuse_session: bool = session is not None
        is_parent = ws.canary_level == 0
        if session is not None and not (ws.sessions_dir / session).exists():
            raise ValueError(f"Session {session} not found in {ws.sessions_dir}")
        now = datetime.datetime.now()
        session_name = session or now.isoformat(timespec="microseconds").replace(":", "-")
        session_dir = ws.sessions_dir / session_name
        jobs = self._make_jobs(specs, session_dir)
        self._select(jobs, only=only)
        ready = self._retarget(jobs, session_dir, inplace=inplace, reused=reuse_session)

        s = Session(name=session_dir.name, prefix=session_dir, jobs=ready, reused=reuse_session)
        if is_parent and not reuse_session:
            config.pluginmanager.hook.canary_sessionstart(session=s)
            s.save()
        return s

    def execute(self, session: Session, *, view_t: ViewSettings | None = None) -> Session:
        """Run a Session returned by :meth:`prepare` and finalize its results."""
        ws = self.workspace
        s = session
        is_parent = ws.canary_level == 0

        # We need to take great care to only write results into the database from the parent
        # process.  On the parent process, create a results listener that looks for results in
        # the spool.  As test jobs finish, the testcase_done_callback is called and the results
        # put into the spool.  When the listener detects the results, it will write them to the
        # database.  This way, the database is only receiving results from a single writer.
        # Otherwise, results can be written from many writers originating from many different
        # processes (eg, a canary instance launched inside a HPC scheduler)
        ws.db.close()
        listener: ResultListener | None = None
        if is_parent:
            listener = ResultListener(db_root=ws.db.root)
            listener.start()
        if view_t is None:
            last = ws.latest_view()
            view_t = last.settings if last is not None else ViewSettings.default()
        view_manager = ViewManager(workspace=ws, session=s, settings=view_t)
        ws.view_manager = view_manager
        try:
            view_manager.start()
            s.run(workspace=ws)
        finally:
            ws.view_manager = None
            if listener is not None:
                listener.stop_and_join()
                # Persist the authoritative final in-memory state of every job.
                # Running/pending rows may have been spooled mid-run; writing the
                # final state here overwrites them so the DB reflects the true
                # outcome.  ``s.jobs`` are the same objects the runner executed.
                if s.jobs:
                    ws.db.put_results(*s.jobs)
                # Any rows still non-terminal (e.g. the run was killed and a job
                # never reported a terminal state) are flipped to a failure so we
                # never leave phantom "running" jobs persisted in the database.
                try:
                    ws.db.reconcile_running_jobs(s.name)
                except Exception:
                    logger.exception("Failed to reconcile non-terminal jobs for session %s", s.name)
            view = view_manager.finish()
            if view is not None:
                ws.register_view(view)
        if is_parent and not s.reused:
            config.pluginmanager.hook.canary_sessionfinish(session=s)
            s.save()
        if is_parent:
            self.register_latest_session(s)
        return s

    def _make_jobs(self, specs: list["JobSpec"], session_dir: Path) -> list[Job]:
        """Construct jobs for *specs*; nested processes refresh masked jobs from lock files."""
        jobs = self.reconstructor.construct_jobs(specs, session_dir)
        if self.workspace.canary_level != 0:
            refresh_masked_jobs(jobs)
        return jobs

    def _select(self, jobs: list[Job], *, only: str) -> None:
        """Apply runtime selection rules; masks jobs in place and resets unmasked ones."""
        selector = select.RuntimeSelector(jobs, workspace=self.workspace.root)
        selector.add_rule(rules.ResourceCapacityRule())
        selector.add_rule(rules.RerunRule(strategy=only))
        timeout = config.get_timeout_option("session")
        if timeout is None:
            timeout = config.get("run:timeout:session")
        if timeout is not None and float(timeout) >= 0.0:
            if fac := config.get_timeout_option("multiplier"):
                timeout *= fac
            selector.add_rule(rules.SessionTimeoutRule(timeout=timeout))
        selector.run()

    def _retarget(
        self, jobs: list[Job], session_dir: Path, *, inplace: bool, reused: bool
    ) -> list[Job]:
        """Return the unmasked jobs, moved into *session_dir* unless running in place.

        At this point jobs have been reconstructed and, if previous results exist,
        restored to their last ran state.  In place, a job is left where it is;
        otherwise its old session is swapped for the new one.
        """
        ready: list[Job] = []
        for job in jobs:
            if job.mask:
                continue
            elif inplace:
                if not job.workspace.dir.exists():
                    raise RuntimeError(f"{job}: requested to run in place but results do not exist")
            else:
                old_dir = job.workspace.dir
                job.workspace.root = session_dir
                job.workspace.session = session_dir.name
                replace_session_dir_variables(job, old=old_dir, new=job.workspace.dir)
                if reused:
                    assert job.workspace.session == session_dir.name, f"{job}: unexpected workspace"
            ready.append(job)
        return ready

    def register_latest_session(self, session: Session) -> None:
        """Update latest results, view, and refs with results from ``session``"""
        # Write meta data file refs/latest -> ../sessions/{session.root}
        refs_dir = self.workspace.refs_dir
        refs_dir.mkdir(parents=True, exist_ok=True)  # may be absent on a loaded workspace
        file = refs_dir / "latest"
        link = os.path.relpath(str(session.prefix), str(file.parent))
        atomic_write(file, str(link))

    def testcase_done_callback(self, event: "ExecutionEvent") -> None:
        """Callback to queue job results for database persistence.

        Results are spooled to the database not only when a job finishes but
        also when it is submitted or starts running, so that ``canary status``
        (which reads the results database) reflects in-progress jobs mid-run.
        :meth:`~_canary.persistence.database.WorkspaceDatabase.put_results` is
        order-independent, so each transition replaces the previous row for
        that job only if it is newer.

        Args:
            event: The execution event.
        """
        if event.name not in ("job_submitted", "job_started", "job_finished"):
            return
        if event.slot is None:
            return
        job = event.slot.job
        if not isinstance(job, Job):
            return
        ws = self.workspace
        ws.db.queue.put(job)
        if ws.view_manager is not None:
            try:
                ws.view_manager.sync(job)
            except Exception:
                logger.exception(f"Failed to update live view for job {job.id}")


def replace_session_dir_variables(job: Job, *, old: Path, new: Path) -> None:
    """Rewrite ``PYTHONPATH``/``PATH`` entries that point at the old session directory.

    Args:
        job: The job whose variables to update.
        old: Old session directory path.
        new: New session directory path.
    """
    variables = job.variables
    old_s, new_s = str(old), str(new)
    for key in _SESSION_DIR_VARIABLES:
        value = variables.get(key)
        if not isinstance(value, str):
            continue
        if value == old_s:
            variables[key] = new_s
        elif value.startswith(old_s + os.pathsep):
            variables[key] = new_s + value[len(old_s) :]


def refresh_masked_jobs(jobs: list[Job]) -> None:
    """Reload state of masked jobs from lock files.

    Nested canary processes (for example, ``canary hpc exec`` running inside
    a scheduler allocation) load upstream results from the workspace
    database, which only the top-level process writes, and it writes them
    asynchronously.  The lock file is written directly by whichever process
    ran the job, so it is the most current record of a job that this
    process will not run itself.  Jobs without a lock file are left as
    constructed.

    Args:
        jobs: Jobs constructed for this run.  Only masked jobs are refreshed.
    """
    for job in jobs:
        if not job.mask or not job.lockfile.exists():
            continue
        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh job %s from its lock file", job.id[:7], exc_info=True)
