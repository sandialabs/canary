# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import sys
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from typing import Callable
from typing import Protocol
from typing import cast

import canary
from _canary.queue_executor import ExecutionSlot
from _canary.reporter import EventReporter
from _canary.reporter import LiveReporter
from _canary.timekeeper import Timekeeper
from _canary.util.misc import boolean

logger = canary.get_logger(__name__)


import canary


class RunnerLike(Protocol):
    jobs: list[canary.Job]
    session: str
    workspace: Any


@dataclass
class FluxJob:
    """
    Lightweight reporter-facing wrapper around an inner Canary Job.

    The inner job remains authoritative for execution, dependency state,
    status, persistence, database updates, and view updates.

    This object's Timekeeper tracks the outer Flux JobSpecV1 lifecycle:

      open   -> allocation requested
      stage  -> individual Flux JobSpecV1 submitted
      start  -> Flux job-start callback
      stop   -> inner Canary job finished
      finish -> parent observed Flux future result
    """

    inner: canary.Job
    allocation_requested_at: float = -1.0
    allocation_granted_at: float = -1.0
    flux_jobid: str | None = None
    timekeeper: Timekeeper = field(default_factory=Timekeeper)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    @property
    def id(self) -> str:
        return self.inner.id

    @property
    def status(self) -> Any:
        return self.inner.status

    @status.setter
    def status(self, value: Any) -> None:
        self.inner.status = value

    @property
    def state(self) -> Any:
        return self.inner.state

    @property
    def measurements(self) -> Any:
        return self.inner.measurements

    def display_name(self, **kwargs: Any) -> str:
        return self.inner.display_name(**kwargs)

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        self.inner.set_status(category=category, outcome=outcome, reason=reason, code=code)

    def save(self) -> None:
        self.inner.save()

    def refresh(self) -> None:
        self.inner.refresh()

    def is_runnable(self) -> bool:
        return self.inner.is_runnable()

    def is_ready(self) -> bool:
        return self.inner.is_ready()

    def is_done(self) -> bool:
        return self.inner.is_done()

    def total_timeout(self) -> float:
        return self.inner.total_timeout()

    def on_submit(self, at: float | None = None) -> None:
        self.timekeeper.open(at=at)

    def on_stage(self, at: float | None = None) -> None:
        self.timekeeper.stage(at=at)

    def on_start(self, at: float | None = None) -> None:
        self.timekeeper.start(at=at)

    def on_stop(self, at: float | None = None) -> None:
        self.timekeeper.stop(at=at)

    def on_finish(self, at: float | None = None) -> None:
        self.timekeeper.close(at=at)


def inner_job(job: canary.BaseJob | FluxJob) -> canary.Job:
    if isinstance(job, FluxJob):
        return job.inner
    return cast(canary.Job, job)


class FluxReporterQueue:
    """
    Minimal queue facade for _canary.queue_executor.LiveReporter/EventReporter.

    This is not a scheduling queue and does not do resource checkout.
    It only provides the queue-shaped methods/attributes the reporters expect.
    """

    def __init__(self, jobs: list[FluxJob]) -> None:
        self._jobs = list(jobs)
        self._jobs = list(jobs)
        self._pending_ids: set[str] = {job.id for job in jobs}
        self._submitted_ids: set[str] = set()
        self._running_ids: set[str] = set()
        self._finished_ids: set[str] = set()

        # EventReporter.__init__ inspects executor.queue._heap to size columns.
        self._heap = [SimpleNamespace(job=job) for job in jobs]

    def jobs(self) -> list[FluxJob]:
        return list(self._jobs)

    def pending(self) -> list[FluxJob]:
        return [job for job in self._jobs if job.id in self._pending_ids]

    def mark_submitted(self, job: FluxJob) -> None:
        self._pending_ids.discard(job.id)
        self._submitted_ids.add(job.id)

    def mark_started(self, job: FluxJob) -> None:
        self._pending_ids.discard(job.id)
        self._submitted_ids.discard(job.id)
        self._running_ids.add(job.id)

    def mark_finished(self, job: FluxJob) -> None:
        self._pending_ids.discard(job.id)
        self._submitted_ids.discard(job.id)
        self._running_ids.discard(job.id)
        self._finished_ids.add(job.id)

    def status(self, start: float | None = None) -> str:
        from collections import Counter

        from _canary.util.time import hhmmss

        total = len(self._jobs)
        pending = len(self._pending_ids)
        submitted = len(self._submitted_ids)
        running = len(self._running_ids)
        done = len(self._finished_ids)

        parts: list[str] = []

        if running:
            parts.append(f"{running}/{total} [green]RUNNING[/]")
        elif submitted:
            parts.append(f"{submitted}/{total} [cyan]SUBMITTED[/]")
        elif pending:
            parts.append(f"{pending}/{total} [magenta]PENDING[/]")
        else:
            parts.append(f"{done}/{total} [blue]COMPLETE[/]")

        totals: Counter[str] = Counter()

        for job in self._jobs:
            if job.id not in self._finished_ids:
                continue
            totals[job.status.display_name(style="rich")] += 1

        for status_name, count in totals.items():
            parts.append(f"{count} {status_name}")

        if start is not None:
            parts.append(f"in {hhmmss(time.time() - start)}")

        return ", ".join(parts)


class FluxDirectExecutor:
    """
    Submit each Canary job as an individual inner Flux job inside an active
    FluxAllocation.

    This reuses the reporter-facing shape from ResourceQueueExecutor.
    """

    def __init__(
        self,
        runner: RunnerLike,
        *,
        time_limit: float = -1.0,
        allocation_requested_at: float = -1.0,
        allocation_granted_at: float = -1.0,
    ) -> None:
        self.runner = runner
        self.time_limit = time_limit
        self.allocation_requested_at = allocation_requested_at
        self.allocation_granted_at = allocation_granted_at

        self.flux_jobs: dict[str, FluxJob] = {
            job.id: FluxJob(
                inner=job,
                allocation_requested_at=allocation_requested_at,
                allocation_granted_at=allocation_granted_at,
            )
            for job in runner.jobs
        }

        self.queue = FluxReporterQueue(list(self.flux_jobs.values()))

        # Scheduling and dependency readiness still use real Canary jobs.
        self.pending: dict[str, canary.Job] = {job.id: job for job in runner.jobs}

        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}

        self.listeners: list[Callable[..., None]] = []
        self.started_on: float = -1.0

        self.futures: dict[Any, str] = {}
        self.slots_by_id: dict[str, ExecutionSlot] = {}

        self.live_reporting = self._should_live_report()
        self.max_concurrent_jobs = int(canary.config.getoption("workers") or -1)

        self._qrank = 0
        self._qsize = len(runner.jobs)

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    def add_listener(self, callback: Callable[..., None]) -> None:
        self.listeners.append(callback)

    def remove_listener(self, callback: Callable[..., None]) -> None:
        try:
            self.listeners.remove(callback)
        except ValueError:
            pass

    def notify_listeners(self, event: str, *args: Any) -> None:
        for callback in list(self.listeners):
            callback(event, *args)

    def run(self) -> int:
        import hpc_connect

        self.started_on = time.time()

        reporter = (
            LiveReporter(self, live_columns="jixpsrfew")
            if self.live_reporting
            else EventReporter(self)
        )
        self.add_listener(self._sync_view_on_finish)
        backend_name = canary.config.getoption("flux_backend") or "flux"
        backend = hpc_connect.get_backend(backend_name)
        submitter = backend.submission_manager()

        for flux_job in self.flux_jobs.values():
            flux_job.on_submit()

        try:
            with reporter:
                while self.pending or self.futures:
                    progress = False

                    progress |= self._submit_ready_jobs(submitter)
                    progress |= self._poll_finished()
                    progress |= self._finalize_blocked_jobs()

                    self._refresh_running_jobs()

                    if not progress:
                        if self.pending and not self.futures:
                            self._finalize_stuck_pending_jobs()
                            break

                        time.sleep(0.25)

                    if (self.time_limit > 0) and (self.started_on + self.time_limit < time.time()):
                        raise TimeoutError("Session time has expired")

        finally:
            self._cancel_remaining()
            self.remove_listener(self._sync_view_on_finish)

        return 0

    def _ready_jobs(self) -> list[canary.Job]:
        ready: list[canary.Job] = []

        for job in list(self.pending.values()):
            job.refresh_readiness()

            # refresh_readiness may mark dependency-failed jobs DONE/BLOCKED.
            if job.state.is_done() or not job.is_runnable():
                continue

            if job.is_ready():
                ready.append(job)

        # Match existing behavior loosely: high-cost jobs first.
        ready.sort(key=lambda job: job.cost(), reverse=True)
        return ready

    def _submit_ready_jobs(self, submitter: Any) -> bool:
        submitted_any = False

        for job in self._ready_jobs():
            if not self._can_submit_more():
                break

            # Remove before submit so we do not double-submit if callbacks/logging
            # re-enter or if loop iterations are fast.
            self.pending.pop(job.id, None)

            self._qrank += 1

            flux_job = self.flux_jobs[job.id]
            slot = ExecutionSlot(
                job=cast(Any, flux_job), qrank=self._qrank, qsize=self._qsize, worker_id=self._qrank
            )

            self.slots_by_id[job.id] = slot

            self._mark_submitted(slot)

            try:
                future = submitter.submit(self._hpc_jobspec(job), exclusive=False)
            except Exception as e:
                logger.exception("Flux submission failed for %s", job.id[:7])
                self._mark_submission_failed(slot, e)
                submitted_any = True
                continue

            self.futures[future] = job.id
            submitted_any = True

            try:
                future.add_jobstart_callback(
                    lambda fut, job_id=job.id: self._mark_flux_started_by_id(job_id)
                )
            except AttributeError:
                pass

            try:
                future.add_jobid_callback(
                    lambda fut, job_id=job.id: self._record_flux_jobid(job_id, fut.jobid)
                )
            except AttributeError:
                pass

        return submitted_any

    def _submit_workspace(self, job: canary.Job) -> Path:
        root = self.runner.workspace.cache_dir / "canary-flux" / self.runner.session / "jobs"
        return root / job.id

    def _can_submit_more(self) -> bool:
        if self.max_concurrent_jobs <= 0:
            return True
        return len(self.futures) < self.max_concurrent_jobs

    def _hpc_jobspec(self, job: canary.Job) -> Any:
        import hpc_connect

        submit_workspace = self._submit_workspace(job)
        submit_workspace.mkdir(parents=True, exist_ok=True)

        command = self._canary_flux_exec_command(job)

        submit_args: list[str] = []
        if extra := canary.config.getoption("flux_submit_args"):
            submit_args.extend(extra)

        return hpc_connect.JobSpec(
            name=f"canary.{job.id[:7]}",
            commands=[command],
            cpus=job.cpus,
            gpus=job.gpus,
            nodes=max(1, job.nodes),
            time_limit=job.total_timeout(),
            env=self._child_environment(job, submit_workspace=submit_workspace),
            output=str(submit_workspace / "flux.out"),
            error=str(submit_workspace / "flux.err"),
            workspace=submit_workspace,
            submit_args=submit_args,
        )

    def _canary_flux_exec_command(self, job: canary.Job) -> str:
        import shlex

        workspace_anchor = self.runner.workspace.root.parent

        args = [sys.executable, "-m", "canary", "-C", str(workspace_anchor)]

        if canary.config.get("debug"):
            args.append("-d")

        args.extend(["flux", "exec", "--session", self.runner.session, job.id])

        return shlex.join(args)

    def _child_environment(
        self, job: canary.Job, *, submit_workspace: Path
    ) -> dict[str, str | None]:
        env: dict[str, str | None] = {}

        level = int(os.getenv("CANARY_LEVEL", "0"))
        env["CANARY_LEVEL"] = str(level + 1)
        env["CANARY_LIVE"] = "0"
        env["CANARY_DISABLE_KB"] = "1"
        env["CANARY_FLUX_DIRECT_JOB"] = job.id
        env["CANARY_FLUX_SUBMIT_WORKSPACE"] = str(submit_workspace)

        try:
            env[canary.config.CONFIG_ENV_CFG64] = canary.config.serialize()
        except Exception:
            logger.debug("Failed to serialize Canary config for child", exc_info=True)

        return env

    def _mark_submitted(self, slot: ExecutionSlot) -> None:
        flux_job = cast(FluxJob, slot.job)
        job = flux_job.inner
        jobspec_submitted_at = time.time()
        slot.on_stage(at=jobspec_submitted_at)
        self.submitted[job.id] = slot
        self.queue.mark_submitted(flux_job)
        try:
            job.add_measurement("flux_jobspec_submitted_at", jobspec_submitted_at)
            job.save()
        except Exception:
            logger.debug("Failed to save submitted job %s", job.id[:7], exc_info=True)
        self.notify_listeners("job_submitted", slot)

    def _mark_flux_started_by_id(self, job_id: str) -> None:
        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return
        flux_job = cast(FluxJob, slot.job)
        job = flux_job.inner
        # Already marked as Flux-started.
        if flux_job.timekeeper._started > 0:
            return
        now = time.time()
        slot.on_start(at=now)
        self.submitted.pop(job.id, None)
        self.running[job.id] = slot
        self.queue.mark_started(flux_job)
        try:
            job.add_measurement("flux_job_started_at", now)
            job.save()
        except Exception:
            logger.debug("Failed to save Flux-started job %s", job_id[:7], exc_info=True)
        self.notify_listeners("job_started", slot)

    def _mark_submission_failed(self, slot: ExecutionSlot, exc: BaseException) -> None:
        flux_job = cast(FluxJob, slot.job)
        job = flux_job.inner

        now = time.time()
        slot.on_finish(at=now)
        job.on_finish(at=now)
        job.set_status(outcome="ERROR", reason=f"Flux submission failed: {exc!r}")

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(flux_job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save submission-failed job %s", job.id[:7], exc_info=True)

        # Parent must persist this because no child flux exec ran.
        try:
            self.runner.workspace.db.queue.put(job)
        except Exception:
            logger.debug("Failed to queue submission-failed job %s", job.id[:7], exc_info=True)

        self.notify_listeners("job_finished", slot)

    def _poll_finished(self) -> bool:
        finished_any = False

        for future, job_id in list(self.futures.items()):
            if not future.done():
                continue

            finished_any = True
            self.futures.pop(future, None)

            rc: int | None = None
            exc: BaseException | None = None
            proc_info: dict[str, Any] = {}

            try:
                rc = future.result()
            except BaseException as e:
                exc = e
            else:
                try:
                    proc_info = future.proc_info(timeout=0)
                except Exception as e:
                    proc_info = {"exception": repr(e)}
                    logger.debug("Failed to read proc_info for %s", job_id[:7], exc_info=True)

            self._mark_finished(job_id, rc=rc, exc=exc, proc_info=proc_info)

        return finished_any

    def _cancel_remaining(self) -> None:
        for future, job_id in list(self.futures.items()):
            try:
                future.cancel()
            except Exception:
                logger.debug("Failed to cancel Flux future for %s", job_id[:7], exc_info=True)
        self.futures.clear()

    def _should_live_report(self) -> bool:
        style = canary.config.getoption("console_style") or {}
        live = style.get("live", True)

        if canary.config.get("debug"):
            live = False
        if not sys.stdin.isatty():
            live = False
        if "CANARY_LIVE" in os.environ and not boolean(os.environ["CANARY_LIVE"]):
            live = False
        elif int(os.getenv("CANARY_LEVEL", "0")) > 0:
            live = False
        elif os.getenv("CANARY_MAKE_DOCS"):
            live = False

        return bool(live)

    def _finalize_blocked_jobs(self) -> bool:
        finalized_any = False

        for job in list(self.pending.values()):
            job.refresh_readiness()

            if not job.state.is_done():
                continue

            # Expected path: refresh_readiness marked it BLOCKED.
            self.pending.pop(job.id, None)

            self._qrank += 1
            now = time.time()

            flux_job = self.flux_jobs[job.id]
            slot = ExecutionSlot(
                job=cast(Any, flux_job), qrank=self._qrank, qsize=self._qsize, worker_id=-1
            )

            slot.on_finish(at=now)
            job.on_finish(at=now)

            self.slots_by_id[job.id] = slot
            self.finished[job.id] = slot
            self.queue.mark_finished(flux_job)

            try:
                job.save()
            except Exception:
                logger.debug("Failed to save blocked job %s", job.id[:7], exc_info=True)

            # Parent must persist blocked jobs because no child will run them.
            try:
                self.runner.workspace.db.queue.put(job)
            except Exception:
                logger.debug("Failed to queue blocked job %s", job.id[:7], exc_info=True)

            self.notify_listeners("job_finished", slot)
            finalized_any = True

        return finalized_any

    def _finalize_stuck_pending_jobs(self) -> None:
        now = time.time()

        for job in list(self.pending.values()):
            self.pending.pop(job.id, None)

            self._qrank += 1

            flux_job = self.flux_jobs[job.id]
            slot = ExecutionSlot(
                job=cast(Any, flux_job), qrank=self._qrank, qsize=self._qsize, worker_id=-1
            )

            slot.on_finish(at=now)
            job.on_finish(at=now)
            job.set_status(
                outcome="BROKEN", reason="Job never became ready and no Flux jobs remain running"
            )

            self.slots_by_id[job.id] = slot
            self.finished[job.id] = slot
            self.queue.mark_finished(flux_job)

            try:
                job.save()
            except Exception:
                logger.debug("Failed to save stuck job %s", job.id[:7], exc_info=True)

            try:
                self.runner.workspace.db.queue.put(job)
            except Exception:
                logger.debug("Failed to queue stuck job %s", job.id[:7], exc_info=True)

            self.notify_listeners("job_finished", slot)

    def _mark_finished(
        self,
        job_id: str,
        *,
        rc: int | None,
        exc: BaseException | None,
        proc_info: dict[str, Any] | None = None,
    ) -> None:
        slot = self.slots_by_id[job_id]
        flux_job = cast(FluxJob, slot.job)
        job = flux_job.inner

        # Pull authoritative status/state/timekeeper/measurements from testcase.lock
        # written by child `canary flux exec`.
        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh finished job %s", job.id[:7], exc_info=True)

        # If the inner Canary lifecycle finished before the Flux future was reaped,
        # record that boundary before closing the FluxJob.
        if job.timekeeper._finished > 0 and flux_job.timekeeper._stopped < 0:
            slot.on_stop(at=job.timekeeper._finished)
            self.notify_listeners("job_stopped", slot)

        returned_at = time.time()
        slot.on_finish(at=returned_at)

        # Attach Flux scheduler/process metadata, if available.
        if proc_info:
            try:
                self._write_proc_info(job, proc_info)
            except Exception:
                logger.debug("Failed to write Flux proc_info for %s", job.id[:7], exc_info=True)

        failure_reason = self._proc_info_failure_reason(proc_info)

        if exc is not None:
            job.set_status(outcome="ERROR", reason=f"Flux job failed: {exc!r}")

        elif rc not in (0, None) and job.status.is_unset():
            if failure_reason:
                job.set_status(outcome="ERROR", reason=f"Flux job failed: {failure_reason}")
            else:
                job.set_status(outcome="ERROR", reason=f"canary flux exec exited with code {rc}")

        elif failure_reason and job.status.is_unset():
            job.set_status(outcome="ERROR", reason=f"Flux job failed: {failure_reason}")

        # Ensure phase is terminal in parent memory. This is what dependents'
        # Dependency.is_done() will see.
        job.on_finish(at=returned_at)

        self._record_flux_timing(job, flux_job, proc_info=proc_info)

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(flux_job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save finished job %s", job.id[:7], exc_info=True)

        # Do NOT queue normal executed jobs here if child `canary flux exec` already
        # did workspace.db.queue.put(job). Parent-side queueing here would duplicate
        # result writes.
        self.notify_listeners("job_finished", slot)

    def _record_flux_timing(
        self, job: canary.Job, flux_job: FluxJob, *, proc_info: dict[str, Any] | None = None
    ) -> None:
        inner_tk = job.timekeeper
        flux_tk = flux_job.timekeeper

        allocation_requested_at = flux_job.allocation_requested_at
        allocation_granted_at = flux_job.allocation_granted_at

        jobspec_submitted_at = flux_tk._staged
        flux_started_at = flux_tk._started
        inner_opened_at = inner_tk._submitted
        inner_started_at = inner_tk._started
        inner_stopped_at = inner_tk._stopped
        inner_finished_at = inner_tk._finished
        flux_finished_at = flux_tk._finished

        launch_seconds = duration(flux_started_at, inner_opened_at)
        return_seconds = duration(inner_finished_at, flux_finished_at)
        return_after_inner_stop_seconds = duration(inner_stopped_at, flux_finished_at)

        flux: dict[str, Any] = {}

        if proc_info:
            flux["proc_info"] = proc_info

        if flux_job.flux_jobid:
            flux["jobid"] = flux_job.flux_jobid

        flux["timing"] = {
            "allocation": {
                "requested_at": allocation_requested_at,
                "granted_at": allocation_granted_at,
                "wait_seconds": duration(allocation_requested_at, allocation_granted_at),
            },
            "jobspec_v1": {
                "submitted_at": jobspec_submitted_at,
                "flux_started_at": flux_started_at,
                "inner_opened_at": inner_opened_at,
                "inner_started_at": inner_started_at,
                "inner_stopped_at": inner_stopped_at,
                "inner_finished_at": inner_finished_at,
                "flux_finished_at": flux_finished_at,
            },
            "durations": {
                # Reporter-facing FluxJob phases
                "allocation_request_to_jobspec_submit_seconds": flux_tk.pending(live=False),
                "jobspec_submit_to_flux_start_seconds": flux_tk.staging(live=False),
                "flux_start_to_inner_finish_seconds": flux_tk.running(live=False),
                "inner_finish_to_flux_return_seconds": flux_tk.finishing(live=False),
                "flux_jobspec_total_seconds": flux_tk.total(live=False),
                # Split out allocation and pre-submit delay.
                "allocation_wait_seconds": duration(allocation_requested_at, allocation_granted_at),
                "allocation_granted_to_jobspec_submit_seconds": duration(
                    allocation_granted_at, jobspec_submitted_at
                ),
                # Inner Canary lifecycle durations.
                "flux_start_to_inner_open_seconds": duration(flux_started_at, inner_opened_at),
                "flux_start_to_inner_start_seconds": duration(flux_started_at, inner_started_at),
                "inner_total_seconds": inner_tk.total(live=False),
                "inner_pending_seconds": inner_tk.pending(live=False),
                "inner_staging_seconds": inner_tk.staging(live=False),
                "inner_command_seconds": inner_tk.running(live=False),
                "inner_finishing_seconds": inner_tk.finishing(live=False),
                # Alternate return overhead boundary using inner command stop.
                "inner_stop_to_flux_return_seconds": return_after_inner_stop_seconds,
            },
        }

        flux["overhead"] = {
            # Primary Flux JobSpecV1 overheads outside the inner Canary lifecycle.
            "launch_seconds": launch_seconds,
            "return_seconds": return_seconds,
            "return_after_inner_stop_seconds": return_after_inner_stop_seconds,
            "total_external_seconds": sum_positive(launch_seconds, return_seconds),
        }

        job.measurements.update({"flux": flux})

    def _record_flux_jobid(self, job_id: str, flux_jobid: str) -> None:
        """
        Record the scheduler job id as soon as hpc_connect/Flux reports it.

        This is best-effort metadata for debugging/reporting; failure here should
        not affect execution.
        """
        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return

        if not flux_jobid or flux_jobid == "unset":
            return

        flux_job = cast(FluxJob, slot.job)
        job = flux_job.inner
        flux_job.flux_jobid = flux_jobid

        try:
            job.add_measurement("flux_jobid", flux_jobid)
            job.save()
        except Exception:
            logger.debug("Failed to save Flux jobid for %s", job_id[:7], exc_info=True)

    def _write_proc_info(self, job: canary.Job, proc_info: dict[str, Any]) -> None:
        """
        Write Flux scheduler/process metadata to the Flux submit workspace.

        This is best-effort debugging metadata. It should not affect job outcome.
        """
        import json

        data = {
            "canary_job_id": job.id,
            "canary_job_name": job.display_name(resolve=True),
            "flux_proc_info": proc_info,
        }

        with job.workspace.openfile("procinfo.json", "w") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)

    def _refresh_running_jobs(self) -> None:
        for slot in list(self.running.values()):
            flux_job = cast(FluxJob, slot.job)
            job = flux_job.inner

            try:
                job.refresh()
            except Exception:
                logger.debug("Failed to refresh running job %s", job.id[:7], exc_info=True)
                continue

            if job.timekeeper._finished > 0 and flux_job.timekeeper._stopped < 0:
                slot.on_stop(at=job.timekeeper._finished)
                self.notify_listeners("job_stopped", slot)

    def _proc_info_failure_reason(self, proc_info: dict[str, Any] | None) -> str | None:
        if not proc_info:
            return None

        errors = proc_info.get("hpc_connect_errors")
        if isinstance(errors, list) and errors:
            parts: list[str] = []

            for item in errors:
                if not isinstance(item, dict):
                    parts.append(repr(item))
                    continue

                kind = item.get("kind", "error")
                message = item.get("message") or item.get("repr") or repr(item)
                parts.append(f"{kind}: {message}")

            return "; ".join(parts)

        flux_exception = proc_info.get("exception")
        if isinstance(flux_exception, dict) and flux_exception.get("occurred"):
            etype = flux_exception.get("type") or "FluxException"
            note = flux_exception.get("note") or ""
            return f"{etype}: {note}".strip()

        error = proc_info.get("error")
        if isinstance(error, str) and error:
            return error

        return None

    def _sync_view_on_finish(self, event: str, slot: ExecutionSlot) -> None:
        if event != "job_finished":
            return

        view_manager = getattr(self.runner.workspace, "view_manager", None)
        if view_manager is None:
            return

        job = inner_job(slot.job)

        try:
            view_manager.sync(job)
        except Exception:
            logger.exception("Failed to sync Flux job %s to results view", job.id[:7])


def duration(start: float, stop: float) -> float:
    if start <= 0 or stop <= 0:
        return -1.0
    return max(0.0, stop - start)


def sum_positive(*values: float) -> float:
    good = [value for value in values if value >= 0.0]
    if not good:
        return -1.0
    return sum(good)
