# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import os
import sys
import time
from pathlib import Path
import hpc_connect
from types import SimpleNamespace
from typing import Any
from typing import Callable
from typing import cast

import canary
from _canary.queue_executor import ExecutionSlot
from _canary.reporter import EventReporter
from _canary.reporter import LiveReporter
from _canary.util.misc import boolean

logger = canary.get_logger(__name__)


@dataclasses.dataclass
class FluxProcRecord:
    """Parent-side record for one submitted Flux job."""

    job_id: str
    proc: Any
    slot: ExecutionSlot
    started_sent: bool = False
    finished_sent: bool = False
    closed: bool = False


class FluxDirectQueue:
    """
    Dependency/readiness queue plus reporter facade for Flux direct execution.

    This queue does not perform resource checkout. Flux owns resource
    management. Canary only cares whether dependencies permit submission.

    The class also provides the queue-shaped methods/attributes expected by
    _canary.reporter.LiveReporter/EventReporter.
    """

    def __init__(self, jobs: list[canary.BaseJob]) -> None:
        self._jobs = list(jobs)
        self._pending: dict[str, canary.Job] = {job.id: cast(canary.Job, job) for job in jobs}
        self._submitted_ids: set[str] = set()
        self._running_ids: set[str] = set()
        self._finished_ids: set[str] = set()

        # EventReporter.__init__ inspects executor.queue._heap to size columns.
        self._heap = [SimpleNamespace(job=job) for job in jobs]

    def __len__(self) -> int:
        return len(self._pending)

    @property
    def pending_by_id(self) -> dict[str, canary.Job]:
        return self._pending

    def has_pending(self) -> bool:
        return bool(self._pending)

    def jobs(self) -> list[canary.BaseJob]:
        return list(self._jobs)

    def pending(self) -> list[canary.BaseJob]:
        return list(self._pending.values())

    def ready_jobs(self) -> list[canary.Job]:
        ready: list[canary.Job] = []

        for job in list(self._pending.values()):
            job.refresh_readiness()

            # refresh_readiness may mark dependency-failed jobs DONE/BLOCKED.
            if job.state.is_done() or not job.is_runnable():
                continue

            if job.is_ready():
                ready.append(job)

        # Preserve current behavior for now: high-cost jobs first.
        ready.sort(key=lambda job: job.cost(), reverse=True)
        return ready

    def claim(self, job: canary.BaseJob) -> None:
        """Remove a job from the pending set because the executor is taking ownership."""
        self._pending.pop(job.id, None)

    def pop_blocked_jobs(self) -> list[canary.Job]:
        """
        Remove and return pending jobs that became terminal while waiting.

        Expected path: Job.refresh_readiness() marks dependency-failed jobs
        DONE/BLOCKED.  The executor remains responsible for turning the returned
        jobs into reporter/listener events.
        """
        blocked: list[canary.Job] = []

        for job in list(self._pending.values()):
            job.refresh_readiness()

            if not job.state.is_done():
                continue

            self._pending.pop(job.id, None)
            blocked.append(job)

        return blocked

    def pop_stuck_pending_jobs(self) -> list[canary.Job]:
        """Remove and return every remaining pending job."""
        jobs = list(self._pending.values())
        self._pending.clear()
        return jobs

    def mark_submitted(self, job: canary.BaseJob) -> None:
        self._pending.pop(job.id, None)
        self._submitted_ids.add(job.id)

    def mark_started(self, job: canary.BaseJob) -> None:
        self._pending.pop(job.id, None)
        self._submitted_ids.discard(job.id)
        self._running_ids.add(job.id)

    def mark_finished(self, job: canary.BaseJob) -> None:
        self._pending.pop(job.id, None)
        self._submitted_ids.discard(job.id)
        self._running_ids.discard(job.id)
        self._finished_ids.add(job.id)

    def status(self, start: float | None = None) -> str:
        from collections import Counter

        from _canary.util.time import hhmmss

        total = len(self._jobs)
        pending = len(self._pending)
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


class FluxReporterQueue(FluxDirectQueue):
    """Backward-compatible name for the reporter-facing Flux queue."""

    pass


class FluxDirectExecutor:
    """
    Submit each Canary job as an individual inner Flux job inside an active
    FluxAllocation.

    This reuses the reporter-facing shape from ResourceQueueExecutor, but does
    not use hpc_connect.Future.  The parent keeps lightweight HPCProcess objects
    and synchronously polls them from the executor loop.

    Timing ownership:

    - parent opens the job when it is submitted to Flux
    - child sets launched when `canary flux exec` begins
    - child sets started/finished around actual job execution
    - parent closes the job when the Flux/HPC process returns

    The parent does not set `timekeeper.launched`.
    """

    def __init__(self, runner: "canary.Runner") -> None:
        self.runner = runner

        # Concern 1: queue of jobs available for Flux submission.  This is a
        # dependency/readiness queue only; Canary does not do Flux resource
        # scheduling or resource checkout here.
        self.queue = FluxDirectQueue(runner.jobs)

        # Reporter-facing state.  These dictionaries reflect actual Canary job
        # state, not merely Flux/HPC process state.
        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}

        self.listeners: list[Callable[..., None]] = []
        self.started_on: float = -1.0

        # Concern 2: submitted Flux processes and polling state.
        self.procs: dict[str, FluxProcRecord] = {}
        self.slots_by_id: dict[str, ExecutionSlot] = {}

        self.live_reporting = self._should_live_report()
        self.num_concurrent_jobs = 50

        self._qrank = 0
        self._qsize = len(runner.jobs)

    @property
    def pending(self) -> dict[str, canary.Job]:
        """Backward-compatible access to pending jobs by id."""
        return self.queue.pending_by_id

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

        self.started_on = time.time()
        for job in self.runner.jobs:
            job.timekeeper.launch(at=self.started_on)
            try:
                job.save()
            except Exception:
                logger.debug("Failed to save opened job %s", job.id[:7], exc_info=True)

        reporter = LiveReporter(self) if self.live_reporting else EventReporter(self)

        self.add_listener(self._sync_view_on_finish)
        backend_name = canary.config.getoption("flux_backend") or "flux"
        backend = hpc_connect.get_backend(backend_name)
        submitter = backend.submission_manager()
        self.num_concurrent_jobs = self.compute_max_concurrent_jobs(backend=backend, default=50)

        logger.info(
            "[bold]Flux direct[/] submit window: %d jobs",
            self.num_concurrent_jobs,
        )

        try:
            with reporter:
                while self.queue.has_pending() or self.procs:
                    progress = False

                    progress |= self._submit_ready_jobs(submitter)
                    progress |= self._poll_processes()
                    progress |= self._refresh_active_jobs()
                    progress |= self._finalize_blocked_jobs()

                    if not progress:
                        if self.queue.has_pending() and not self.procs:
                            self._finalize_stuck_pending_jobs()
                            break

                        time.sleep(0.25)

        finally:
            self._cancel_remaining()
            self.remove_listener(self._sync_view_on_finish)

        return 0

    # ---------------------------------------------------------------------
    # Concern 1 consumer: available-job queue / dependency readiness
    # ---------------------------------------------------------------------

    def _ready_jobs(self) -> list[canary.Job]:
        """Backward-compatible wrapper for tests/callers."""
        return self.queue.ready_jobs()

    def _finalize_blocked_jobs(self) -> bool:
        finalized_any = False

        for job in self.queue.pop_blocked_jobs():
            self._qrank += 1
            now = time.time()
            slot = ExecutionSlot(job=job, qrank=self._qrank, qsize=self._qsize, worker_id=-1)

            if job.timekeeper.opened < 0:
                job.timekeeper.open(at=now)
            if job.timekeeper.launched < 0:
                job.timekeeper.launch(at=now)
            if job.timekeeper.started < 0:
                job.timekeeper.start(at=now)
            if job.timekeeper.finished < 0:
                job.timekeeper.stop(at=now)
            if job.timekeeper.closed < 0:
                job.timekeeper.close(at=now)

            job.on_finished()

            self.slots_by_id[job.id] = slot
            self.finished[job.id] = slot
            self.queue.mark_finished(job)

            try:
                job.save()
            except Exception:
                logger.debug("Failed to save blocked job %s", job.id[:7], exc_info=True)

            # Parent must persist blocked jobs because no child will run them.
            self._queue_parent_result(job, what="blocked")

            self.notify_listeners("job_finished", slot)
            finalized_any = True

        return finalized_any

    def _finalize_stuck_pending_jobs(self) -> None:
        now = time.time()

        for job in self.queue.pop_stuck_pending_jobs():
            self._qrank += 1
            slot = ExecutionSlot(job=job, qrank=self._qrank, qsize=self._qsize, worker_id=-1)

            job.timekeeper.start(at=now)
            job.timekeeper.stop(at=now)
            job.timekeeper.close(at=now)

            job.on_finished()
            job.set_status(
                outcome="BROKEN", reason="Job never became ready and no Flux jobs remain running"
            )

            self.slots_by_id[job.id] = slot
            self.finished[job.id] = slot
            self.queue.mark_finished(job)

            try:
                job.save()
            except Exception:
                logger.debug("Failed to save stuck job %s", job.id[:7], exc_info=True)

            self._queue_parent_result(job, what="stuck")

            self.notify_listeners("job_finished", slot)

    # ---------------------------------------------------------------------
    # Concern 2: Flux submission / polling
    # ---------------------------------------------------------------------

    def _submit_ready_jobs(self, submitter: Any) -> bool:
        submitted_any = False

        for job in self.queue.ready_jobs():
            if not self._can_submit_more():
                break

            # Remove before submit so we do not double-submit if callbacks/logging
            # re-enter or if loop iterations are fast.
            self.queue.claim(job)

            self._qrank += 1
            slot = ExecutionSlot(
                job=job, qrank=self._qrank, qsize=self._qsize, worker_id=self._qrank
            )

            self.slots_by_id[job.id] = slot

            # Parent opens the job before handing it to Flux.  This is the
            # only normal-running timestamp the parent writes before the child
            # process is complete.
            job.on_submitted()

            try:
                job.save()
            except Exception:
                logger.debug("Failed to save opened job %s", job.id[:7], exc_info=True)

            try:
                proc = submitter.popen(self._hpc_jobspec(job), exclusive=False)
            except Exception as e:
                logger.exception("Flux submission failed for %s", job.id[:7])
                self._mark_submission_failed(slot, e)
                submitted_any = True
                continue

            self.procs[job.id] = FluxProcRecord(job_id=job.id, proc=proc, slot=slot)
            self._mark_submitted(slot)
            self._record_flux_jobid(job.id, getattr(proc, "jobid", "unset"))

            submitted_any = True

        return submitted_any

    def _can_submit_more(self) -> bool:
        return len(self.procs) < self.num_concurrent_jobs

    def _poll_processes(self) -> bool:
        progressed = False

        for job_id, record in list(self.procs.items()):
            proc = record.proc

            try:
                rc = proc.poll()
            except BaseException as e:
                logger.exception("Flux poll failed for %s", job_id[:7])
                proc_info = self._capture_proc_info(proc)
                self.procs.pop(job_id, None)
                self._mark_process_closed(
                    job_id,
                    rc=None,
                    exc=e,
                    proc_info=proc_info,
                    parent_queue=True,
                )
                progressed = True
                continue

            self._record_flux_jobid(job_id, getattr(proc, "jobid", "unset"))

            # Do not set timekeeper.launched here.  It is set by the child
            # process and observed via job.refresh().
            returncode = getattr(proc, "returncode", None)
            if rc is None and returncode is None:
                continue

            self.procs.pop(job_id, None)
            proc_info = self._capture_proc_info(proc)
            final_rc = returncode if returncode is not None else rc
            self._mark_process_closed(job_id, rc=final_rc, exc=None, proc_info=proc_info)
            progressed = True

        return progressed

    def _cancel_remaining(self) -> None:
        for job_id, record in list(self.procs.items()):
            try:
                record.proc.cancel()
            except Exception:
                logger.debug("Failed to cancel Flux process for %s", job_id[:7], exc_info=True)

            self.procs.pop(job_id, None)
            proc_info = self._capture_proc_info(record.proc)
            self._mark_cancelled(job_id, proc_info=proc_info)

    def _submit_workspace(self, job: canary.Job) -> Path:
        root = self.runner.workspace.cache_dir / "canary-flux" / self.runner.session / "jobs"
        return root / job.id

    def _hpc_jobspec(self, job: canary.Job) -> Any:

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

    # ---------------------------------------------------------------------
    # State transitions / reporter event emission
    # ---------------------------------------------------------------------

    def _mark_submitted(self, slot: ExecutionSlot) -> None:
        job = slot.job

        self.submitted[job.id] = slot
        self.queue.mark_submitted(job)

        self.notify_listeners("job_submitted", slot)

    def _mark_child_started(self, record: FluxProcRecord) -> bool:
        if record.started_sent:
            return False

        slot = record.slot
        job = slot.job

        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh starting job %s", job.id[:7], exc_info=True)
            return False

        if job.timekeeper.started <= 0:
            return False

        self.submitted.pop(job.id, None)
        self.running[job.id] = slot
        self.queue.mark_started(job)

        record.started_sent = True
        self.notify_listeners("job_started", slot)
        return True

    def _mark_child_finished(self, record: FluxProcRecord) -> bool:
        if record.finished_sent:
            return False

        slot = record.slot
        job = slot.job

        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh finishing job %s", job.id[:7], exc_info=True)
            return False

        if job.timekeeper.finished <= 0:
            return False

        # If we missed the start transition, emit it first so event ordering is
        # preserved.
        if not record.started_sent:
            self.submitted.pop(job.id, None)
            self.running[job.id] = slot
            self.queue.mark_started(job)
            record.started_sent = True
            self.notify_listeners("job_started", slot)

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(job)

        record.finished_sent = True
        self.notify_listeners("job_finished", slot)
        return True

    def _mark_submission_failed(self, slot: ExecutionSlot, exc: BaseException) -> None:
        job = slot.job
        now = time.time()

        if job.timekeeper.opened < 0:
            job.timekeeper.open(at=now)
        if job.timekeeper.launched < 0:
            job.timekeeper.launch(at=now)
        if job.timekeeper.started < 0:
            job.timekeeper.start(at=now)
        if job.timekeeper.finished < 0:
            job.timekeeper.stop(at=now)
        if job.timekeeper.closed < 0:
            job.timekeeper.close(at=now)

        job.on_finished()
        job.set_status(outcome="ERROR", reason=f"Flux submission failed: {exc!r}")

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save submission-failed job %s", job.id[:7], exc_info=True)

        # Parent must persist this because no child flux exec ran.
        self._queue_parent_result(job, what="submission-failed")

        self.notify_listeners("job_finished", slot)

    def _mark_cancelled(
        self,
        job_id: str,
        *,
        proc_info: dict[str, Any] | None = None,
        reason: str = "Cancelled remaining Flux job",
    ) -> None:
        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return

        job = slot.job
        now = time.time()

        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh cancelled job %s", job.id[:7], exc_info=True)

        if proc_info:
            try:
                job.measurements.update({"flux": proc_info})
            except Exception:
                logger.debug("Failed to attach Flux proc_info to %s", job.id[:7], exc_info=True)

            try:
                self._write_proc_info(cast(canary.Job, job), proc_info)
            except Exception:
                logger.debug("Failed to write Flux proc_info for %s", job.id[:7], exc_info=True)

        job.timekeeper.close(at=now)
        job.on_finished()
        job.set_status(outcome="CANCELLED", reason=reason)

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save cancelled job %s", job.id[:7], exc_info=True)

        # Parent must persist cancelled jobs; the child may never write a final result.
        self._queue_parent_result(job, what="cancelled")

        self.notify_listeners("job_finished", slot)

    def _mark_process_closed(
        self,
        job_id: str,
        *,
        rc: int | None,
        exc: BaseException | None,
        proc_info: dict[str, Any] | None = None,
        parent_queue: bool = False,
    ) -> None:
        slot = self.slots_by_id[job_id]
        job = slot.job

        # Pull authoritative status/state/timekeeper/measurements from testcase.lock
        # written by child `canary flux exec`.
        try:
            job.refresh()
        except Exception:
            logger.debug("Failed to refresh closed job %s", job.id[:7], exc_info=True)

        if proc_info:
            try:
                job.measurements.update({"flux": proc_info})
            except Exception:
                logger.debug("Failed to attach Flux proc_info to %s", job.id[:7], exc_info=True)

            try:
                self._write_proc_info(cast(canary.Job, job), proc_info)
            except Exception:
                logger.debug("Failed to write Flux proc_info for %s", job.id[:7], exc_info=True)

        failure_reason = self._proc_info_failure_reason(proc_info)

        if exc is not None:
            job.set_status(outcome="ERROR", reason=f"Flux job failed: {exc!r}")
            parent_queue = True

        elif rc == 0 and job.status.is_unset():
            job.set_status(
                outcome="ERROR",
                reason=(
                    "Flux job exited successfully, but no Canary result was recorded. "
                    "The child testcase.lock was missing, stale, or unreadable."
                ),
            )
            parent_queue = True

        elif rc not in (0, None) and job.status.is_unset():
            if failure_reason:
                job.set_status(outcome="ERROR", reason=f"Flux job failed: {failure_reason}")
            else:
                job.set_status(outcome="ERROR", reason=f"canary flux exec exited with code {rc}")
            parent_queue = True

        elif failure_reason and job.status.is_unset():
            job.set_status(outcome="ERROR", reason=f"Flux job failed: {failure_reason}")
            parent_queue = True

        # Parent closes the lifecycle when the Flux/HPC process has returned.
        job.timekeeper.close(at=time.time())

        # Ensure phase is terminal in parent memory. This is what dependents'
        # Dependency.is_done() will see.
        job.on_finished()

        record = FluxProcRecord(job_id=job_id, proc=None, slot=slot)
        existing = None
        # The process record may already have been popped by _poll_processes.
        # Preserve event semantics by emitting missing child events if needed.
        if job_id in self.procs:
            existing = self.procs[job_id]

        event_record = existing or record
        if not event_record.started_sent and job.timekeeper.started > 0:
            self.submitted.pop(job.id, None)
            self.running[job.id] = slot
            self.queue.mark_started(job)
            event_record.started_sent = True
            self.notify_listeners("job_started", slot)

        if not event_record.finished_sent:
            self.submitted.pop(job.id, None)
            self.running.pop(job.id, None)
            self.finished[job.id] = slot
            self.queue.mark_finished(job)
            event_record.finished_sent = True
            self.notify_listeners("job_finished", slot)
        else:
            self.submitted.pop(job.id, None)
            self.running.pop(job.id, None)
            self.finished[job.id] = slot
            self.queue.mark_finished(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save closed job %s", job.id[:7], exc_info=True)

        # Queue parent-side result after close so DB can capture the closed time
        # and process metadata.  This may replace the child-written row.
        self._queue_parent_result(job, what="closed" if not parent_queue else "parent-finished")

    def _refresh_active_jobs(self) -> bool:
        progressed = False

        for record in list(self.procs.values()):
            # Refresh child-written lifecycle state.
            if self._mark_child_started(record):
                progressed = True

            if self._mark_child_finished(record):
                progressed = True

        return progressed

    # ---------------------------------------------------------------------
    # Metadata helpers
    # ---------------------------------------------------------------------

    def _record_flux_jobid(self, job_id: str, flux_jobid: str) -> None:
        """
        Record the scheduler job id as in-memory metadata.

        This is deliberately not saved while the child process is running, to
        avoid clobbering the child-owned testcase.lock.
        """
        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return

        if not flux_jobid or flux_jobid == "unset":
            return

        job = slot.job

        try:
            data = getattr(job.measurements, "data", {})
            if isinstance(data, dict) and data.get("flux_jobid") == flux_jobid:
                return
            job.add_measurement("flux_jobid", flux_jobid)
        except Exception:
            logger.debug("Failed to record Flux jobid for %s", job_id[:7], exc_info=True)

    def _capture_proc_info(self, proc: Any) -> dict[str, Any]:
        try:
            proc.capture_completion_info()
        except Exception:
            logger.debug("Failed to capture Flux completion info", exc_info=True)

        info = getattr(proc, "completion_info", None)
        if isinstance(info, dict):
            return dict(info)
        return {}

    def _write_proc_info(self, job: canary.Job, proc_info: dict[str, Any]) -> None:
        """
        Write Flux scheduler/process metadata to the job workspace.

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

    # ---------------------------------------------------------------------
    # Reporting / view / persistence helpers
    # ---------------------------------------------------------------------

    def _sync_view_on_finish(self, event: str, slot: ExecutionSlot) -> None:
        if event != "job_finished":
            return

        view_manager = getattr(self.runner.workspace, "view_manager", None)
        if view_manager is None:
            return

        try:
            view_manager.sync(cast(canary.Job, slot.job))
        except Exception:
            logger.exception("Failed to sync Flux job %s to results view", slot.job.id[:7])

    def _queue_parent_result(self, job: canary.BaseJob, *, what: str) -> None:
        try:
            self.runner.workspace.db.queue.put(job)
        except Exception:
            logger.debug("Failed to queue %s job %s", what, job.id[:7], exc_info=True)

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

    def compute_max_concurrent_jobs(self, *, backend: hpc_connect.Backend | None = None, default: int = 50) -> int:
        explicit = canary.config.getoption("flux_max_concurrent_jobs")
        if explicit is not None:
            return int(explicit)
        if backend is not None:
            node_count = backend.node_count
            cpus_per_node = backend.count_per_node("cpus")
            return node_count * cpus_per_node
        return int(default)
