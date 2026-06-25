# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import subprocess
import threading
from pathlib import Path
from types import TracebackType

import hpc_connect

import canary

logger = canary.get_logger(__name__)


class UnsupportedBackend(RuntimeError):
    def __init__(self, backend: str, supported_backends: list[str] = []):
        super().__init__(
            f"Unsupported backend {backend} (supported backends: {supported_backends})"
        )


def bootstrap_flux_jobspec(
    backend_name: str,
    nodes: int,
    time_limit: float,
    workspace: Path = Path.cwd(),
) -> hpc_connect.JobSpec:
    submit_args: list[str] = []
    commands: list[str] = []

    supported_backends = ["flux"]

    match backend_name:
        case "flux":
            commands = ["sleep infinity"]
        case _:
            raise UnsupportedBackend(backend_name, supported_backends=supported_backends)

    spec = hpc_connect.JobSpec(
        name="bootstrap-flux",
        commands=commands,
        nodes=nodes,
        time_limit=time_limit,
        env=os.environ.copy(),
        submit_args=submit_args,
        output=str(workspace / "bootstrap-flux.log"),
        workspace=workspace,
    )

    return spec


class FailedFluxAllocStartup(Exception):
    pass


class FluxAllocation:
    def __init__(
        self,
        scheduler: str,
        nodes: int = 1,
        queue_timeout: float = 1200,
        time_limit: float = 1200,
        workspace: Path = Path.cwd(),
    ) -> None:
        self._submitted_event = threading.Event()
        self._start_event = threading.Event()
        self._flux_uri = os.environ.get("FLUX_URI")

        self.nodes = nodes
        self.queue_timeout = queue_timeout
        self.time_limit = time_limit
        self.spec = bootstrap_flux_jobspec(scheduler, nodes, time_limit, workspace)
        self.backend = hpc_connect.get_backend(scheduler)

    def _mark_job_submitted(self, job: hpc_connect.Future) -> None:
        self._submitted_event.set()

    def _mark_job_start(self, job: hpc_connect.Future) -> None:
        self._start_event.set()

    def submit(self) -> None:
        self.job = self.backend.submission_manager().submit(spec=self.spec)
        self.job.add_jobid_callback(self._mark_job_submitted)
        self.job.add_jobstart_callback(self._mark_job_start)

    def wait_for_start(self) -> None:
        submission_timeout = 3 * self.job._polling_interval
        if not self._submitted_event.wait(timeout=submission_timeout):
            raise RuntimeError(
                f"Exceeded FluxAllocation submission timeout ({submission_timeout}s)"
            )
        progress = logger.progress_monitor(
            f"Waiting for FluxAllocation job {self.job.jobid} to start"
        )
        if not self._start_event.wait(timeout=self.queue_timeout):
            raise RuntimeError(f"Exceeded Flux start timeout ({self.queue_timeout}s)")
        progress.done()

    def set_flux_uri(self) -> None:
        uri_command = ["flux", "uri", "--remote", self.job.jobid]
        os.environ["FLUX_URI"] = subprocess.check_output(uri_command, text=True)
        logger.info(f"Set FLUX_URI to {os.environ['FLUX_URI']}")

    def shutdown(self) -> None:
        self.job.cancel()

    def __enter__(self) -> "FluxAllocation":
        try:
            self.submit()
            self.wait_for_start()
            self.set_flux_uri()
            return self

        except Exception as e:
            self.shutdown()
            raise FailedFluxAllocStartup(f"Failed to start FluxAllocation {self.job.jobid}")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ):
        self.shutdown()
        return False
