import os
import sys
import time

import hpc_connect
import shlex

from _canary.job import Job, JobPhase
from _canary.runtest import Runner
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


class JobExecutor:
    def __init__(self):
        self.submitter = hpc_connect.get_backend("flux").submission_manager()
        self.job_env = create_job_env()

    def __call__(self, job: Job) -> hpc_connect.Future:
        def format_status_string(hpc_id: str, status: str | None = None):
            status = status or job.status.display_name(style="rich")
            job_name = job.display_name(style="rich", resolve=False)
            job_id = job.id[:7]
            return f"{job_name}  {job_id}  {hpc_id} {status}"

        def job_submitted(fut: hpc_connect.Future):
            logger.info(format_status_string(fut.jobid, "[cyan]SUBMITTED[/]"))
            job.timekeeper.submitted = time.time()

        def job_started(fut: hpc_connect.Future):
            logger.info(format_status_string(fut.jobid, "[green]RUNNING[/]"))
            job.timekeeper.started = time.time()

        def job_finished(fut: hpc_connect.Future):
            job.refresh()
            logger.info(format_status_string(fut.jobid))
            job.state.phase = JobPhase.DONE
            job.save()

        spec = self.hpc_jobspec(job)
        fut = self.submitter.submit(spec, exclusive=False)
        fut.add_jobid_callback(job_submitted)
        fut.add_jobstart_callback(job_started)
        fut.add_done_callback(job_finished)
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
        with FluxAllocation("flux"):
            extor = JobExecutor()
            for job in runner.jobs:
                try:
                    f = extor(job)
                    futures.append(f)
                except hpc_connect.SubmissionFailedError:
                    pass
            for f in hpc_connect.futures.as_completed(futures):
                continue
        return True
