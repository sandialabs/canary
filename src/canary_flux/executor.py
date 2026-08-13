# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

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


class FluxExecutionSlot(ExecutionSlot):
    """
    ExecutionSlot with Flux-specific timing semantics.

    For Flux:
      - submitted/spawned represent parent-side submission time.
      - started represents when Flux says the job started, or when the child
        testcase.lock reports test start.
      - elapsed means actual runtime only.
      - queued means time waiting before start.
    """

    def queued(self) -> float:
        base = self.submitted if self.submitted > 0 else self.spawned

        if self.started > 0:
            return self.started - base

        return time.time() - base

    def elapsed(self) -> float:
        if self.started < 0:
            return -1.0

        end = self.finished if self.finished >= 0 else time.time()
        return end - self.started

    def running(self) -> float:
        if self.started < 0:
            return -1.0

        end = self.finished if self.finished >= 0 else time.time()
        return end - self.started


class FluxReporterQueue:
    """
    Minimal queue facade for _canary.queue_executor.LiveReporter/EventReporter.

    This is not a scheduling queue and does not do resource checkout.
    It only provides the queue-shaped methods/attributes the reporters expect.
    """

    def __init__(self, jobs: list[canary.BaseJob]) -> None:
        self._jobs = list(jobs)
        self._pending_ids: set[str] = {job.id for job in jobs}
        self._submitted_ids: set[str] = set()
        self._running_ids: set[str] = set()
        self._finished_ids: set[str] = set()

        # EventReporter.__init__ inspects executor.queue._heap to size columns.
        self._heap = [SimpleNamespace(job=job) for job in jobs]

    def jobs(self) -> list[canary.BaseJob]:
        return list(self._jobs)

    def pending(self) -> list[canary.BaseJob]:
        return [job for job in self._jobs if job.id in self._pending_ids]

    def mark_submitted(self, job: canary.BaseJob) -> None:
        self._pending_ids.discard(job.id)
        self._submitted_ids.add(job.id)

    def mark_started(self, job: canary.BaseJob) -> None:
        self._pending_ids.discard(job.id)
        self._submitted_ids.discard(job.id)
        self._running_ids.add(job.id)

    def mark_finished(self, job: canary.BaseJob) -> None:
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

    def __init__(self, runner: "canary.Runner") -> None:
        self.runner = runner
        self.queue = FluxReporterQueue(runner.jobs)

        self.pending: dict[str, canary.Job] = {job.id: job for job in runner.jobs}

        self.submitted: dict[str, ExecutionSlot] = {}
        self.running: dict[str, ExecutionSlot] = {}
        self.finished: dict[str, ExecutionSlot] = {}

        self.listeners: list[Callable[..., None]] = []
        self.started_on: float = -1.0

        self.futures: dict[Any, str] = {}
        self.slots_by_id: dict[str, ExecutionSlot] = {}

        self.live_reporting = self._should_live_report()
        self.max_submitted = int(canary.config.getoption("flux_max_submitted") or 0)

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

        reporter = LiveReporter(self) if self.live_reporting else EventReporter(self)

        backend_name = canary.config.getoption("flux_backend") or "flux"
        logger.info("FLUX_URI before hpc_connect.get_backend: %s", os.environ.get("FLUX_URI"))
        backend = hpc_connect.get_backend(backend_name)
        submitter = backend.submission_manager()

        try:
            with reporter:
                while self.pending or self.futures:
                    progress = False

                    progress |= self._submit_ready_jobs(submitter)
                    progress |= self._poll_finished()
                    progress |= self._finalize_blocked_jobs()

                    if not progress:
                        if self.pending and not self.futures:
                            self._finalize_stuck_pending_jobs()
                            break

                        time.sleep(0.25)

        finally:
            self._cancel_remaining()

        return 0

    def _ready_jobs(self) -> list["canary.Job"]:
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
            slot = FluxExecutionSlot(
                job=job,
                qrank=self._qrank,
                qsize=self._qsize,
                spawned=time.time(),
                worker_id=self._qrank,
            )

            self.slots_by_id[job.id] = slot

            try:
                future = submitter.submit(self._hpc_jobspec(job), exclusive=False)
            except Exception as e:
                logger.exception("Flux submission failed for %s", job.id[:7])
                self._mark_submission_failed(slot, e)
                submitted_any = True
                continue

            self.futures[future] = job.id
            self._mark_submitted(slot)
            submitted_any = True

            try:
                future.add_jobstart_callback(
                    lambda fut, job_id=job.id: self._mark_started_by_id(job_id)
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

    def _submit_workspace(self, job: "canary.Job") -> Path:
        root = self.runner.workspace.cache_dir / "canary-flux" / self.runner.session / "jobs"
        return root / job.id

    def _can_submit_more(self) -> bool:
        if self.max_submitted <= 0:
            return True
        return len(self.futures) < self.max_submitted

    def _hpc_jobspec(self, job: "canary.Job") -> Any:
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

    def _canary_flux_exec_command(self, job: "canary.Job") -> str:
        import shlex

        workspace_anchor = self.runner.workspace.root.parent

        args = [sys.executable, "-m", "canary", "-C", str(workspace_anchor)]

        if canary.config.get("debug"):
            args.append("-d")

        args.extend(["flux", "exec", "--session", self.runner.session, job.id])

        return shlex.join(args)

    def _child_environment(
        self, job: "canary.Job", *, submit_workspace: Path
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
        job = slot.job
        now = time.time()

        slot.submitted = now
        job.timekeeper.submitted = now
        job.on_submitted()

        self.submitted[job.id] = slot
        self.queue.mark_submitted(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save submitted job %s", job.id[:7], exc_info=True)

        self.notify_listeners("job_submitted", slot)

    def _mark_started_by_id(self, job_id: str) -> None:
        slot = self.slots_by_id.get(job_id)
        if slot is None:
            return
        if job_id in self.running:
            return

        job = slot.job
        now = time.time()

        slot.started = now
        job.timekeeper.started = now
        job.on_started()

        self.submitted.pop(job.id, None)
        self.running[job.id] = slot
        self.queue.mark_started(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save started job %s", job.id[:7], exc_info=True)

        self.notify_listeners("job_started", slot)

    def _mark_submission_failed(self, slot: ExecutionSlot, exc: BaseException) -> None:
        job = slot.job
        now = time.time()

        slot.submitted = now
        slot.started = now
        slot.finished = now

        job.timekeeper.submitted = now
        job.timekeeper.started = now
        job.timekeeper.finished = now
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
                    proc_info = {"proc_info_error": repr(e)}
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
            slot = ExecutionSlot(
                job=job, qrank=self._qrank, qsize=self._qsize, spawned=now, worker_id=-1
            )

            slot.submitted = now
            slot.started = now
            slot.finished = now

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
            slot = ExecutionSlot(
                job=job, qrank=self._qrank, qsize=self._qsize, spawned=now, worker_id=-1
            )

            slot.submitted = now
            slot.started = now
            slot.finished = now

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
                self._write_proc_info(cast("canary.Job", job), proc_info)
            except Exception:
                logger.debug("Failed to write Flux proc_info for %s", job.id[:7], exc_info=True)

        # If the Flux future itself failed, prefer that reason.
        if exc is not None:
            job.set_status(outcome="ERROR", reason=f"Flux job failed: {exc!r}")

        # If the child command returned nonzero but did not leave a Canary status,
        # synthesize an ERROR.
        elif rc not in (0, None) and job.status.is_unset():
            job.set_status(outcome="ERROR", reason=f"canary flux exec exited with code {rc}")

        now = time.time()

        # Preserve start time from the child lock file if available.
        if slot.started < 0 and job.timekeeper.started > 0:
            slot.started = job.timekeeper.started

        # If no start callback ever fired, make elapsed accounting sane.
        if slot.started < 0:
            slot.started = job.timekeeper.started if job.timekeeper.started > 0 else now

        slot.finished = now

        if job.timekeeper.submitted < 0:
            job.timekeeper.submitted = slot.submitted if slot.submitted > 0 else now
        if job.timekeeper.started < 0:
            job.timekeeper.started = slot.started
        if job.timekeeper.finished < 0:
            job.timekeeper.finished = now

        # Ensure phase is terminal in parent memory. This is what dependents'
        # Dependency.is_done() will see.
        job.on_finished()

        self._sync_finished_slot_times_from_job(slot)

        self.submitted.pop(job.id, None)
        self.running.pop(job.id, None)
        self.finished[job.id] = slot
        self.queue.mark_finished(job)

        try:
            job.save()
        except Exception:
            logger.debug("Failed to save finished job %s", job.id[:7], exc_info=True)

        # Do NOT queue normal executed jobs here if child `canary flux exec` already
        # did workspace.db.queue.put(job). Parent-side queueing here would duplicate
        # result writes.
        self.notify_listeners("job_finished", slot)

    def _sync_finished_slot_times_from_job(self, slot: ExecutionSlot) -> None:
        """
        Sync slot timing from the child's testcase.lock without destroying
        Flux queue-time information.

        FluxExecutionSlot.elapsed() uses started/finished for actual runtime,
        while queued() uses submitted/spawned -> started.
        """
        job = slot.job
        tk = job.timekeeper

        if tk.submitted > 0:
            slot.submitted = tk.submitted

        if tk.started > 0:
            slot.started = tk.started

        if tk.finished > 0:
            slot.finished = tk.finished
        else:
            slot.finished = time.time()

        if slot.started < 0:
            slot.started = slot.finished

        if job.timekeeper.submitted < 0:
            job.timekeeper.submitted = slot.submitted if slot.submitted > 0 else slot.spawned
        if job.timekeeper.started < 0:
            job.timekeeper.started = slot.started
        if job.timekeeper.finished < 0:
            job.timekeeper.finished = slot.finished

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

    def _write_proc_info(self, job: "canary.Job", proc_info: dict[str, Any]) -> None:
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
