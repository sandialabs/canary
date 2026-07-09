# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import os
import shlex
import sys
import time
from typing import TYPE_CHECKING
from typing import Generator

import hpc_connect
import hpc_connect.futures

import canary
import canary_hpc.batchexec as be
from _canary.util.multiprocessing import SimpleQueue

if TYPE_CHECKING:
    from .batchspec import TestBatch

logger = canary.get_logger(__name__)


class HPCConnectDistRunner(be.HPCConnectRunner):
    def execute(self, batch: "TestBatch", queue: SimpleQueue) -> int | None:  # type: ignore[override]
        started_at: float = -1.0

        def set_starttime(future):
            nonlocal started_at
            now = time.time()
            started_at = now
            batch.timekeeper.started = now
            queue.put(
                {"event": "job_started", "timestamp": now, "host": getattr(batch, "hostname", None)}
            )

        def set_jobid(future):
            batch.jobid = future.jobid

        logger.debug(f"Starting {batch} on pid {os.getpid()}")

        with batch.workspace.enter():
            try:
                future = self.submit(batch)
            except Exception:
                logger.exception(f"Error submitting {batch}")
                raise
            future.add_jobstart_callback(set_starttime)
            future.add_jobid_callback(set_jobid)

            submitted_at = (
                batch.timekeeper.submitted if batch.timekeeper.submitted > 0 else time.time()
            )
            queue_deadline = submitted_at + batch.queue_timeout
            run_timeout = float(batch.estimated_runtime() * batch.timeout_multiplier)
            poll = max(1.0, getattr(future, "_polling_interval", 1.0))

            with self.handle_signals([future], batch):
                while True:
                    if future.done():
                        rc = future.result()
                        logger.debug(f"Finished {batch} with exit code {rc}")
                        return rc

                    now = time.time()

                    if started_at < 0.0:
                        if now >= queue_deadline:
                            future.cancel()
                            raise TimeoutError(
                                f"Batch {batch.id[:7]} exceeded queue timeout "
                                f"{batch.queue_timeout:.1f}s"
                            )
                        time.sleep(poll)
                        continue

                    remaining = (started_at + run_timeout) - now
                    if remaining <= 0:
                        future.cancel()
                        raise TimeoutError(
                            f"Batch {batch.id[:7]} exceeded run timeout {run_timeout:.1f}s"
                        )

                    try:
                        rc = future.result(timeout=min(poll, remaining))
                    except TimeoutError:
                        continue
                    else:
                        logger.debug(f"Finished {batch} with exit code {rc}")
                        return rc

    def rc_environ(self, batch: "TestBatch") -> dict[str, str | None]:  # type: ignore[override]
        variables = super().rc_environ(batch)
        variables.update({"__CANARY_DIST_EXEC": "1", "PYTHONEXEC": sys.executable})
        export = canary.config.getoption("dist_export") or {}
        if export.get("ALL") == "==YES==":
            variables.update(self.filtered_env())
        else:
            for var, value in export.items():
                if value == "==YES==":
                    if env_value := os.getenv(var):
                        variables[var] = env_value
                else:
                    variables[var] = str(value)
        return variables

    @staticmethod
    def filtered_env() -> Generator[tuple[str, str], None, None]:
        for key, val in os.environ.items():
            if key.startswith(("_", "BASH_FUNC_")):
                continue
            if key in ("USER", "HOME", "PS1"):
                continue
            yield (key, val)

    def submit(self, batch: "TestBatch") -> hpc_connect.futures.Future:
        assert self.backend.name == "remote_subprocess"

        variables = self.rc_environ(batch)
        invocation = self.canary_invocation(batch)

        job = hpc_connect.JobSpec(
            name=f"canary.{batch.id[:7]}",
            commands=[invocation],
            cpus=batch.cpus,
            time_limit=batch.estimated_runtime() * batch.timeout_multiplier,
            env=variables,
            output=str(batch.workspace.joinpath(batch.stdout)),
            error=str(batch.workspace.joinpath(batch.stdout)),
            workspace=batch.workspace.dir,
            extensions={"remote_subprocess": {"host": batch.hostname}},
        )

        try:
            future = self.backend.submission_manager().submit(job)
        except Exception:
            logger.exception(f"Submission for job {job} failed")
            raise

        return future

    def canary_invocation(self, batch: "TestBatch") -> str:
        """Write the canary invocation used to run this batch."""
        default_args = ["-C", str(batch.workspace.dir)]

        if canary.config.get("debug"):
            default_args.append("-d")

        args: list[str] = [sys.executable, "-m", "canary", *default_args, "dist", "exec"]
        n = canary.config.getoption("dist_remote_workers") or -1
        args.extend([f"--workers={n}", f"--workspace={batch.workspace.dir}"])
        return shlex.join(args)
