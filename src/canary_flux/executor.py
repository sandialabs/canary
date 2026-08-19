# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import dataclasses
import os
import sys
import time
from pathlib import Path
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

    @property
    def pending_by_id(self) -> dict[str, canary.Job]:
        return self._pending

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


class FluxDirectExecutor:
    """
    Submit each Canary job as an individual inner Flux job inside an active
    FluxAllocation.

    This reuses the reporter-facing shape from ResourceQueueExecutor, but does
    not use hpc_connect.Future.  The parent keeps lightweight HPCProcess objects
    and synchronously polls them from the executor loop.
    """

    def __init__(self, runner: "canary.Runner") -> None:
        self.runner = runner

        # Concern 1: queue of jobs available for Flux submission.  This is a
        # dependency/readiness queue only; Canary does not do Flux resource
        # scheduling or resource checkout here.
        self.queue = FluxDirectQueue(runner.jobs)

        # Reporter-facing state.
        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}

        self.listeners: list[Callable[..., None]] = []
        self.started_on: float = -1.0

        # Concern 2: submitted Flux processes and polling state.
        self.procs: dict[str, FluxProcRecord] = {}
        self.slots_by_id: dict[str, ExecutionSlot] = {}

        self.live_reporting = self._should_live_report()
        self.max_concurrent_jobs = self._configured_max_concurrent_jobs(default=50)

        self._qrank = 0
        self._qsize = len(runner.jobs)

    @property
    def inflight(self) -> dict[str, ExecutionSlot]:
        return self.submitted | self.running

    @property
    def pending(self) -> dict[str, canary.Job]:
        return self.queue.pending_by_id

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

        reporter = LiveReporter(self) if self.live_reporting else EventReporter(self)

        self.add_listener(self._sync_view_on_finish)
        backend_name = canary.config.getoption("flux_backend") or "flux"
        backend = hpc_connect.get_backend(backend_name)
        submitter = backend.submission_manager()

        if not hasattr(submitter, "popen"):
            raise RuntimeError(
                "canary_flux direct execution requires hpc_connect.HPCSubmissionManager.popen(...)"
            )

        try:
            with reporter:
                while self.queue.has_pending() or self.procs:
                    progress = False

                    progress |= self._submit_ready_jobs(submitter)
                    progress |= self._poll_finished()
                    progress |= self._finalize_blocked_jobs()

                    self._refresh_running_jobs()

                    if not progress:
                        if self.queue.has_pending() and not self.procs:
                            self._finalize_stuck_pending_jobs()
                            break

                        time.sleep(0.25)

        finally:
            self._cancel_remaining()
            self.remove_listener(self._sync_view_on_finish)

        return 0

    def _ready_jobs(self) -> list[canary.Job]:
        return self.queue.ready_jobs()

    def _finalize_blocked_jobs(self) -> bool:
        finalized_any = False

        for job in self.queue.pop_blocked_jobs():
            # Expected path: refresh_readiness marked it BLOCKED.
            self._qrank += 1
            now = time.time()
            slot = ExecutionSlot(job=job, qrank=self._qrank, qsize=self._qsize, worker_id=-1)
            slot.timer.stop(at=now)

            if job.timekeeper.submitted < 0:
                job.timekeeper.submitted = now
            if job.timekeeper.started < 0:
                job.timekeeper.started = now
            if job.timekeeper.finished < 0:
                job.timekeeper.finished = now

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
            slot.timer.stop(at=now)

            job.timekeeper.submitted = now
            job.timekeeper.started = now
            job.timekeeper.finished = now
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

            try:
                proc = submitter.popen(self._hpc_jobspec(job), exclusive=False)
            except Exception as e:
                logger.exception("Flux submission failed for %s", job.id[:7])
                self._mark_submission_failed(slot, e)
                submitted_any = True
                continue

            self.procs[job.id] = FluxProcRecord(job_id=job.id, proc=proc, slot=slot)
            self._mark_submitted(slot, proc=proc)
            self._record_flux_jobid(job.id, getattr(proc, "jobid", "unset"))

            submitted_any = True

        return submitted_any

    def _can_submit_more(self) -> bool:
        return len(self.procs) < self.max_concurrent_jobs

    def _poll_finished(self) -> bool:
        progressed = False

        for job_id, record in list(self.procs.items()):
            proc = record.proc

            try:
                rc = proc.poll()
            except BaseException as e:
                logger.exception("Flux poll failed for %s", job_id[:7])
                proc_info = self._capture_proc_info(proc)
                self.procs.pop(job_id, None)
                self._mark_finished(job_id, rc=None, exc=e, proc_info=proc_info, parent_queue=True)
                progressed = True
                continue

            self._record_flux_jobid(job_id, getattr(proc, "jobid", "unset"))

            started = getattr(proc, "started", -1.0)
            if started > 0:
                if self._mark_started_by_id(job_id, at=started):
                    progressed = True

            returncode = getattr(proc, "returncode", None)
            if rc is None and returncode is None:
                continue

            self.procs.pop(job_id, None)
            proc_info = self._capture_proc_info(proc)
            final_rc = returncode if returncode is not None else rc
            self._mark_finished(job_id, rc=final_rc, exc=None, proc_info=proc_info)
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

    def _mark_submitted(self, slot: ExecutionSlot, *, proc: Any | None = None) -> None:
        job = slot.job
        submitted_at = getattr(proc, "submitted", -1.0) if proc is not None else -1.0
        if submitted_at <= 0:
            submitted_at = time.time()

        # Restart Queued at actual Flux submission time.
        slot.timer.start("Queued", at=submitted_at)
        job.timekeeper.submitted = submitted_at
        job.on_submitted()

        self.submitted[job.id] = slot
        self.queue.mark_submitted(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save submitted job %s", job.id[:7], exc_info=True)

        self.notify_listeners("job_submitted", slot)

    def _mark_started_by_id(self, job_id: str, *, at: float | None = None) -> bool:
        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return False
        if job_id in self.running:
            return False

        job = slot.job
        now = time.time() if at is None or at <= 0 else float(at)

        # Queued -> Startup.  This is scheduler-running state, not actual
        # command start.  The actual test command start is read from testcase.lock
        # by _refresh_running_jobs / _sync_finished_slot_times_from_job.
        if slot.timer.current == "Queued":
            slot.timer.transition("Startup", at=now)

        job.on_started()

        self.submitted.pop(job.id, None)
        self.running[job.id] = slot
        self.queue.mark_started(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save started job %s", job.id[:7], exc_info=True)

        self.notify_listeners("job_started", slot)
        return True

    def _mark_submission_failed(self, slot: ExecutionSlot, exc: BaseException) -> None:
        job = slot.job
        now = time.time()

        slot.timer.stop(at=now)
        job.timekeeper.finished = now
        if job.timekeeper.submitted < 0:
            job.timekeeper.submitted = now

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

        # Best effort: capture any partial child timing/status first, but the
        # parent outcome remains CANCELLED because the parent explicitly cancelled it.
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

        if job.timekeeper.submitted < 0:
            job.timekeeper.submitted = now

        job.on_finished()
        job.set_status(outcome="CANCELLED", reason=reason)

        self._sync_finished_slot_times_from_job(slot)
        self._record_flux_timing(cast(canary.Job, job), slot)

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

    def _mark_finished(
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
            logger.debug("Failed to refresh finished job %s", job.id[:7], exc_info=True)

        # Attach Flux scheduler/process metadata, if available.
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

        elif rc not in (0, None) and job.status.is_unset():
            if failure_reason:
                job.set_status(outcome="ERROR", reason=f"Flux job failed: {failure_reason}")
            else:
                job.set_status(outcome="ERROR", reason=f"canary flux exec exited with code {rc}")

        elif failure_reason and job.status.is_unset():
            job.set_status(outcome="ERROR", reason=f"Flux job failed: {failure_reason}")

        # Ensure phase is terminal in parent memory. This is what dependents'
        # Dependency.is_done() will see.
        job.on_finished()

        self._sync_finished_slot_times_from_job(slot)
        self._record_flux_timing(cast(canary.Job, job), slot)

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save finished job %s", job.id[:7], exc_info=True)

        # Normal executed jobs are expected to be queued by child `canary flux exec`.
        # Parent-side queueing is used only for parent-synthesized terminal states
        # such as poll failure.
        if parent_queue:
            self._queue_parent_result(job, what="parent-finished")

        self.notify_listeners("job_finished", slot)

    def _refresh_running_jobs(self) -> None:
        for slot in list(self.running.values()):
            job = slot.job

            try:
                job.refresh()
            except Exception:
                logger.debug("Failed to refresh running job %s", job.id[:7], exc_info=True)
            else:
                tk = job.timekeeper

                # Startup -> Running when the child command starts.
                if tk.started > 0 and slot.timer.current in ("Queued", "Startup"):
                    slot.timer.transition("Running", at=tk.started)

                # Running -> Teardown if the child has already finished but the
                # process has not yet been reaped by the parent.
                if tk.finished > 0 and slot.timer.current == "Running":
                    slot.timer.transition("Teardown", at=tk.finished)

    def _sync_finished_slot_times_from_job(self, slot: ExecutionSlot) -> None:
        job = slot.job
        tk = job.timekeeper

        if tk.started > 0 and slot.timer.current in ("Queued", "Startup"):
            slot.timer.transition("Running", at=tk.started)

        if tk.finished > 0 and slot.timer.current == "Running":
            slot.timer.transition("Teardown", at=tk.finished)

        slot.timer.stop(at=time.time())

    def _record_flux_timing(self, job: canary.Job, slot: ExecutionSlot) -> None:
        phases = ("Queued", "Startup", "Running", "Teardown")

        timing = {
            "phases": {name: slot.phase_time(name, live=False) for name in phases},
            "elapsed": slot.total_time(phases, live=False),
        }

        # Optional flat keys for compatibility/convenience.
        timing.update(
            {
                "queue_time": slot.phase_time("Queued", live=False),
                "startup_time": slot.phase_time("Startup", live=False),
                "execution_time": slot.phase_time("Running", live=False),
                "teardown_time": slot.phase_time("Teardown", live=False),
                "elapsed_time": slot.total_time(phases, live=False),
            }
        )

        job.measurements.update({"flux_timing": timing})

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

        job = slot.job

        try:
            job.add_measurement("flux_jobid", flux_jobid)
        except Exception:
            logger.debug("Failed to record Flux jobid for %s", job_id[:7], exc_info=True)
            return

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save Flux jobid for %s", job_id[:7], exc_info=True)

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

    def _configured_max_concurrent_jobs(self, *, default: int) -> int:
        value: Any = None

        try:
            value = canary.config.getoption("flux_max_concurrent_jobs")
        except Exception:
            value = None

        if value is None:
            try:
                value = canary.config.getoption("workers")
            except Exception:
                value = None

        if value is None:
            return int(default)

        try:
            n = int(cast(Any, value))
        except Exception:
            return int(default)

        if n <= 0:
            return int(default)

        return n
