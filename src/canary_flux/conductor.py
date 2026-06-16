import sys

import hpc_connect
import shlex

from _canary.job import Job
from _canary.runtest import Runner
import canary
from canary_flux.flux_alloc import FluxAllocation


class FluxConductor:
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
        return hpc_connect.JobSpec(
            name=job.id,
            commands=[self.canary_invocation(job)],
            cpus=job.cpus,
            gpus=job.gpus,
            time_limit=job.total_timeout(),
        )

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
        return hpc_connect.JobSpec(
            name=job.id,
            commands=[self.canary_invocation(job)],
            cpus=job.cpus,
            gpus=job.gpus,
            time_limit=job.total_timeout(),
        )

    @canary.hookimpl(tryfirst=True)
    def canary_runtests(self, runner: Runner) -> bool:
        futures: list[hpc_connect.Future] = []
        with FluxAllocation("flux"):
            submitter = hpc_connect.get_backend("flux").submission_manager()
            for job in runner.jobs:
                try:
                    f = submitter.submit(self.hpc_jobspec(job), exclusive=False)
                    futures.append(f)
                except hpc_connect.SubmissionFailedError:
                    pass
            for f in hpc_connect.futures.as_completed(futures):
                continue
        return True
