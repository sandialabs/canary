import os
import shlex
import sys
import threading
import time
from collections import Counter
from typing import Any

import hpc_connect

import _canary.job_queue as job_queue
import canary
from _canary import reporter
from _canary.job import BaseJob
from _canary.job import Job
from _canary.runtest import Runner
from _canary.util.time import hhmmss
from canary_flux.flux_alloc import FluxAllocation

logger = canary.get_logger(__name__)


def create_job_env() -> dict[str, str]:
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


class Busy(Exception):
    pass


class Empty(Exception):
    pass


class JobQueue(job_queue.JobQueue):
    def __init__(self, jobs: list[Job], lock: threading.Lock):
        super().__init__()
        self.lock = lock
        self.qsize = len(jobs)
        self.started_on = time.time()
        self._pending: dict[str, Job] = {job.id: job for job in jobs}

    def __len__(self) -> int:
        return self.qsize

    def _get_job(self) -> BaseJob:
        if not self._pending:
            raise Empty

        for id, job in self._pending.items():
            if job.is_ready():
                self._pending.pop(id)
                return job
        else:
            raise Busy

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
            done = len(self.finished)
            busy = len(self.running)
            pending = len(self._pending)
            total = done + busy + pending
            totals: Counter[tuple[Category, Outcome]] = Counter()
            for es in self.finished.values():
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


class JobExecutor:
    def __init__(self, queue: job_queue.JobQueue):
        self.submitter = hpc_connect.get_backend("flux").submission_manager()
        self.job_env = create_job_env()
        self.queue = queue

    def __call__(self, rank) -> hpc_connect.Future:
        slot = self.queue.get(qrank=rank)
        assert isinstance(slot.job, Job)
        spec = self.hpc_jobspec(slot.job)
        fut = self.submitter.submit(spec, exclusive=False)

        job_id = slot.job.id
        self.queue.update({"job_id": job_id, "event": "job_submitted"})
        fut.add_jobstart_callback(
            lambda f: self.queue.update({"job_id": job_id, "event": "job_started"})
        )
        fut.add_done_callback(
            lambda f: self.queue.update({"job_id": job_id, "event": "job_finished"})
        )
        return fut

    def canary_invocation(self, job: Job) -> str:
        assert job.workspace.session
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


def flux_alloc_opts() -> dict[str, Any]:
    opts: dict[str, Any] = {}
    opts["scheduler"] = canary.config.getoption("canary_flux_scheduler")
    opts["queue_timeout"] = canary.config.getoption("canary_flux_queue_timeout")
    opts["nodes"] = canary.config.getoption("canary_flux_nodes")
    opts["time_limit"] = canary.config.getoption("canary_flux_time_limit")

    logger.debug(f"FluxAllocation options: {opts}")
    return opts


class FluxConductor:
    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: Runner) -> bool:
        try:
            futures: list[hpc_connect.Future] = []
            style = canary.config.getoption("console_style") or {}
            live_reporting = style.get("live", True)
            qm = JobQueue(runner.jobs, global_lock)
            rep = reporter.LiveReporter(qm) if live_reporting else reporter.EventReporter(qm)
            with FluxAllocation(
                **flux_alloc_opts(),
                workspace=runner.workspace.sessions_dir / runner.session,
            ):
                extor = JobExecutor(qm)
                rank = 1
                with rep:
                    while True:
                        try:
                            f = extor(rank)
                            futures.append(f)
                            rank += 1
                        except hpc_connect.SubmissionFailedError:
                            pass
                        except Busy:
                            time.sleep(3)
                            continue
                        except Empty:
                            break
                    for f in hpc_connect.futures.as_completed(futures):
                        continue
        except Exception as e:
            logger.exception(e)
        return True
