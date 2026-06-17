from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
import threading
import time
from typing import Iterable

import hpc_connect
import shlex

from _canary import reporter
from _canary.job import BaseJob, Job, JobPhase
from _canary.runtest import Runner
from _canary.util.time import hhmmss
import canary
from canary_flux.flux_alloc import FluxAllocation

logger = canary.get_logger(__name__)


def create_job_env() -> dict[str, str | None]:
    level = int(os.getenv("CANARY_LEVEL", "0"))
    variables = {
        "CANARY_LEVEL": str(level + 1),
        "CANARY_DISABLE_KB": "1",
        "CANARY_LIVE": "0",
    }

    if canary.config.get("debug"):
        variables["CANARY_DEBUG"] = "on"
    return variables

global_lock = threading.Lock()


class QueueMonitor(reporter.ReportableExecutor):
    def __init__(self, jobs: Iterable[Job], lock: threading.Lock):
        super().__init__()
        self.lock = lock
        self.qsize = len(jobs)
        self.start_time: float = time.time()
        self._pending: dict[str, Job] = {job.id: job for job in jobs}
        self._submitted: dict[str, reporter.ExecutionSlot] = {}
        self._running: dict[str, reporter.ExecutionSlot] = {}
        self._finished: dict[str, reporter.ExecutionSlot] = {}

    @property
    def started_on(self) -> float:
        return self.start_time

    @property
    def submitted(self) -> dict[str, reporter.ExecutionSlot]:
        return self._submitted

    @property
    def running(self) -> dict[str, reporter.ExecutionSlot]:
        return self._running

    @property
    def finished(self) -> dict[str, reporter.ExecutionSlot]:
        return self._finished

    def jobs(self) -> list[BaseJob]:
        all_jobs: list[BaseJob] = self.pending()
        all_jobs.extend([es.job for es in self.submitted.values()])
        all_jobs.extend([es.job for es in self.running.values()])
        all_jobs.extend([es.job for es in self.finished.values()])
        return all_jobs

    def pending(self) -> list[BaseJob]:
        return list(self._pending.values())

    def status(self, start: float | None = None) -> str:
        from _canary.status import Category
        from _canary.status import Outcome

        def sortkey(x):
            n = 0 if x[0] == Category.PASS else 2 if x[0] == Category.FAIL else 1
            return (n, x[1])

        with self.lock:
            done = len(self._finished)
            busy = len(self._running)
            pending = len(self._pending)
            total = done + busy + pending
            totals: Counter[tuple[Category, Outcome]] = Counter()
            for es in self._finished.values():
                job = es.job
                if job.state.is_done():
                    key = (job.status.category, job.status.outcome)
                    totals[key] += 1
            row: list[str] = []
            if pending:
                row.append(f"{busy}/{total} [green]RUNNING[/]")
            else:
                row.append(f"{done}/{total} [blue]COMPLETE[/]")
            for key in sorted(totals, key=sortkey):
                color = key[0].rich_color()
                row.append(f"{totals[key]} [{color}]{key[1].name}[/]")
            if start is not None:
                duration = hhmmss(time.time() - start)
                row.append(f"in {duration}")
            return ", ".join(row)


class QueueCallbacks:
    def __init__(self, queue_monitor: QueueMonitor):
        self.qm = queue_monitor

    def on_submitted(self, job_id: str):
        with self.qm.lock:
            job = self.qm._pending.pop(job_id)
        es = reporter.ExecutionSlot(
            job=job,
            qrank=-1,
            qsize=self.qm.qsize,
            spawned=time.time(),
            worker_id=-1,
            submitted=time.time(),
        )
        es.job.on_submitted()
        with self.qm.lock:
            self.qm._submitted[job.id] = es
        self.qm.notify_listeners("job_submitted", es)

    def on_started(self, job_id: str):
        with self.qm.lock:
            es = self.qm._submitted.pop(job_id)
            es.started = time.time()
            self.qm._running[job_id] = es
        es.job.on_started()
        self.qm.notify_listeners("job_finished", es)

    def on_finished(self, job_id: str):
        with self.qm.lock:
            es = self.qm._running.pop(job_id)
            es.finished = time.time()
            self.qm._finished[job_id] = es

        es.job.refresh()
        es.job.on_finished()
        # es.job.timekeeper.submitted = es.submitted
        # es.job.timekeeper.started = es.started
        # es.job.timekeeper.finished = es.finished
        es.job.save()
        self.qm.notify_listeners("job_finished", es)


class JobExecutor:

    def __init__(self, qm: QueueMonitor):
        self.submitter = hpc_connect.get_backend("flux").submission_manager()
        self.job_env = create_job_env()
        self.cb = QueueCallbacks(qm)

    def __call__(self, job: Job) -> hpc_connect.Future:
        spec = self.hpc_jobspec(job)
        fut = self.submitter.submit(spec, exclusive=False)

        job_id = job.id
        self.cb.on_submitted(job_id)
        fut.add_jobstart_callback(lambda f: self.cb.on_started(job_id))
        fut.add_done_callback(lambda f: self.cb.on_finished(job_id))
        return fut

    def canary_invocation(self, job: Job) -> str:
        args: list[str] = [
            sys.executable,
            "-m",
            "canary",
            "exec",
            "--session",
            job.workspace.session,
            job.id,
        ]
        return shlex.join(args)

    def hpc_jobspec(self, job: Job) -> hpc_connect.JobSpec:
        job.workspace.create(exist_ok=True)
        return hpc_connect.JobSpec(
            name=job.id,
            commands=[self.canary_invocation(job)],
            cpus=job.cpus,
            gpus=job.gpus,
            time_limit=job.total_timeout(),
            env=self.job_env,
            workspace=job.workspace.dir,
            output=str(job.workspace.dir / "job-output.txt"),
        )


class FluxConductor:
    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: Runner) -> bool:
        futures: list[hpc_connect.Future] = []
        style = canary.config.getoption("console_style") or {}
        live_reporting = False  # style.get("live", True)
        qm = QueueMonitor(runner.jobs, global_lock)
        rep = (
            reporter.LiveReporter(qm) if live_reporting else reporter.EventReporter(qm)
        )
        with FluxAllocation("flux"):
            extor = JobExecutor(qm)
            with rep:
                for job in runner.jobs:
                    try:
                        f = extor(job)
                        futures.append(f)
                    except hpc_connect.SubmissionFailedError:
                        pass
                for f in hpc_connect.futures.as_completed(futures):
                    continue
        return True
