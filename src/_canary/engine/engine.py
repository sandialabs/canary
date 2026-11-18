# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""
Session preparation and execution.

:class:`Engine` splits running a session into two phases:

* :meth:`Engine.prepare` -- specs -> Jobs, runtime selection, session-directory
  retargeting, and the :class:`~_canary.workspace.session.Session` manifest.
* :meth:`Engine.execute` -- result listener, live view, the run itself, and
  finalization (persist final state, reconcile, hooks, ``refs/latest``).

``Engine.run()`` is ``execute(prepare(...))``.  The engine also collects and selects specs
(:mod:`~_canary.engine.collection`, :mod:`~_canary.engine.selection`).
"""

import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Callable
from typing import Literal

from .. import config
from .. import select
from ..core import rules
from ..core.job import Job
from ..error import StopExecution
from ..error import notests_exit_status
from ..execution.context import ExecutionContext
from ..execution.runtest import JobExecutor
from ..execution.runtest import Runner
from ..execution.runtest import canary_runtests
from ..persistence.listener import ResultListener
from ..util import logging
from ..util.filesystem import atomic_write
from ..view import ViewManager
from ..view import ViewSettings
from ..workspace.session import Session
from .collection import collect_specs
from .jobs import construct_jobs
from .jobs import refresh_masked_jobs
from .selection import SpecSelector

if TYPE_CHECKING:
    from ..core.jobspec import JobSpec
    from ..workspace.workspace import Workspace

logger = logging.get_logger(__name__)

#: An observer receives each raw executor event dict, with the job under ``"job"``.
JobEventObserver = Callable[[dict], None]

_SESSION_DIR_VARIABLES = ("PYTHONPATH", "PATH")


class Engine:
    """Prepare and execute test sessions for a :class:`Workspace`."""

    def __init__(self, workspace: "Workspace") -> None:
        self.workspace = workspace
        self.selector = SpecSelector(workspace.root, workspace.db)

    def collect(
        self,
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        parsing_policy: Literal["pedantic", "permissive"] = "pedantic",
    ) -> list["JobSpec"]:
        """Collect specs from *scanpaths* into this workspace (see :func:`collect_specs`)."""
        return collect_specs(
            self.workspace.root, self.workspace.db, scanpaths, on_options, parsing_policy
        )

    def select(
        self,
        tag: str,
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Select specs from the database, save as *tag* (see :meth:`SpecSelector.select`)."""
        return self.selector.select(tag, prefixes, keyword_exprs, parameter_expr, owners, regex)

    def select_from_specs(
        self,
        resolved: list["JobSpec"],
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        extra_rules: list["rules.Rule"] | None = None,
    ) -> list["JobSpec"]:
        """Filter *resolved* specs (see :meth:`SpecSelector.select_from_specs`)."""
        return self.selector.select_from_specs(
            resolved, prefixes, keyword_exprs, parameter_expr, owners, regex, extra_rules
        )

    def select_from_tag(
        self,
        tag: str,
        source_tag: str,
        prefixes: list[str] | None = None,
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Create *tag* by filtering *source_tag* (see :meth:`SpecSelector.select_from_tag`)."""
        return self.selector.select_from_tag(
            tag, source_tag, prefixes, keyword_exprs, parameter_expr, owners, regex
        )

    def create_selection(
        self,
        tag: str | None,
        scanpaths: dict[str, list[str]],
        on_options: list[str] | None = None,
        parsing_policy: Literal["pedantic", "permissive"] = "pedantic",
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
    ) -> list["JobSpec"]:
        """Collects generators from paths and creates a tagged selection.

        Args:
            tag: Tag name (randomly generated if None).
            scanpaths: Paths to scan for generators.
            on_options: Options to filter tests by.
            keyword_exprs: Filter by keywords.
            parameter_expr: Filter by parameters.
            owners: Filter by owners.
            regex: Filter by regex.

        Returns:
            The created selection of JobSpecs.
        """
        specs = self.collect(scanpaths, on_options=on_options, parsing_policy=parsing_policy)
        return self.selector.create_selection(
            tag,
            specs,
            scanpaths,
            on_options=on_options,
            keyword_exprs=keyword_exprs,
            parameter_expr=parameter_expr,
            owners=owners,
            regex=regex,
        )

    def apply_selection_rules(
        self,
        specs: list["JobSpec"],
        keyword_exprs: list[str] | None = None,
        parameter_expr: str | None = None,
        owners: list[str] | None = None,
        regex: str | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Filter *specs* in place (see :meth:`SpecSelector.apply_selection_rules`)."""
        return self.selector.apply_selection_rules(
            specs, keyword_exprs, parameter_expr, owners, regex, ids
        )

    def run(
        self,
        specs: list["JobSpec"],
        session: str | None = None,
        inplace: bool = False,
        view_t: ViewSettings | None = None,
        only: str = "not_pass",
    ) -> Session:
        """Executes a set of job specifications in a new or existing session.

        Args:
            specs: List of job specs to run.
            session: Optional existing session name to reuse.
            inplace: If True, run jobs in their existing result directories.
            view_t: View settings.
            only: Rerun strategy (e.g., 'not_pass').

        Returns:
            The resulting Session object.
        """
        s = self.prepare(specs, session=session, inplace=inplace, only=only)
        return self.execute(s, view_t=view_t)

    def job_for(self, spec_id: str, *, session: str | None = None) -> Job:
        """Build the job for *spec_id* (with its upstreams) in *session*, ready to run again.

        Args:
            spec_id: Spec ID, ID prefix, or matching pattern.
            session: Session directory name; a new timestamped name by default.
        """
        ws = self.workspace
        session_dir = ws.sessions_dir / (session or _new_session_name())
        spec = ws.find_jobspec(spec_id)
        specs = ws.db.load_specs(ids=[spec.id], include_upstreams=True)
        job = next(j for j in construct_jobs(ws, specs, session_dir) if j.id == spec.id)
        job.status.reset()
        job.state.reset()
        return job

    def exec_job(self, job: Job, *, observer: JobEventObserver | None = None) -> Job:
        """Run one job directly, outside the session scheduler, and record its result.

        The job runs through :class:`~_canary.execution.runtest.JobExecutor` (the same
        lifecycle as a scheduled job).  A job that is not ready has its readiness
        refreshed: if an upstream outcome blocks it, it is recorded as BLOCKED and
        returned without running.  Results are written to the database by the
        parent process and spooled for the parent's listener by nested processes.

        Args:
            job: A job from :meth:`job_for`.
            observer: Called with each executor event (the event dict plus the job
                under ``"job"``), for live status rendering.

        Raises:
            RuntimeError: If the job is not ready and could still run later (an
                upstream has not finished).
        """
        if job.is_ready():
            JobExecutor()(job, _PhaseTrackingSink(job, observer))
        else:
            job.refresh_readiness()
            if not job.state.is_done():
                raise RuntimeError(f"{job}: job is not ready to run")
            job.save()
        if self.workspace.canary_level == 0:
            self.workspace.db.put_results(job)
        else:
            self.workspace.db.queue.put(job)
        return job

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
        session_name = session or _new_session_name()
        session_dir = ws.sessions_dir / session_name
        jobs = self.build_jobs(specs, session_dir)
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
        # the spool.  As test jobs finish, the context's ``record`` callback puts the results
        # into the spool.  When the listener detects the results, it will write them to the
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
        view_manager = ViewManager(
            root=ws.root.parent,
            cache_dir=ws.cache_dir,
            settings=view_t,
            jobs=s.jobs,
            load_jobs=ws.load_jobs,
        )
        try:
            if live_view := view_manager.start():
                ws.register_view(live_view)
            self._run_session(s, self._context(view_manager), parent=is_parent)
        finally:
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

    def build_jobs(self, specs: list["JobSpec"], session_dir: Path) -> list[Job]:
        """Construct jobs for *specs*; nested processes refresh masked jobs from lock files."""
        jobs = construct_jobs(self.workspace, specs, session_dir)
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

    def _run_session(self, session: Session, context: ExecutionContext, *, parent: bool) -> None:
        """Run the runnable jobs of *session* through the ``canary_runtests`` hooks."""
        session.prefix.mkdir(parents=True, exist_ok=True)
        ready = [job for job in session.jobs if job.is_runnable()]
        runner = Runner(ready, session.name, context=context)

        if not ready:
            exit_code = 0 if config.getoption("empty_ok") else notests_exit_status
            raise StopExecution("no jobs to run", exit_code=exit_code)

        parent_session = parent
        starting_dir = os.getcwd()
        try:
            session.started_on = datetime.datetime.now()
            if parent_session:
                session.save()
            os.chdir(str(session.prefix))
            canary_runtests(runner=runner)
        except Exception:
            logger.exception("session run failed")
            session.returncode = 1
        finally:
            session.finished_on = datetime.datetime.now()
            os.chdir(starting_dir)
            session.returncode = runner.returncode
            if parent_session:
                session.save()

    def _context(self, view_manager: ViewManager) -> ExecutionContext:
        """Return the context a backend runs a session with (see :class:`ExecutionContext`)."""
        ws = self.workspace

        def record(job: Job) -> None:
            ws.db.queue.put(job)
            try:
                view_manager.sync(job)
            except Exception:
                logger.exception(f"Failed to update live view for job {job.id}")

        return ExecutionContext(
            root=ws.root,
            sessions_dir=ws.sessions_dir,
            cache_dir=ws.cache_dir,
            reports_dir=ws.reports_dir,
            record=record,
        )


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


def _new_session_name() -> str:
    """Return a filesystem-safe, timestamped session name."""
    now = datetime.datetime.now()
    return now.isoformat(timespec="microseconds").replace(":", "-")


class _PhaseTrackingSink:
    """Advance a job's lifecycle from executor events, forwarding each to an observer.

    :class:`~_canary.execution.runtest.JobExecutor` drives a job by ``put``-ing event
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
