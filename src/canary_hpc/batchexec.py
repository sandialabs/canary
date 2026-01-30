# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import math
import os
import shlex
import signal
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Generator
from typing import Protocol

import hpc_connect
import hpc_connect.futures

import canary

if TYPE_CHECKING:
    from .batchspec import TestBatch


logger = canary.get_logger(__name__)


class Cancellable(Protocol):
    def cancel(self) -> None: ...


class HPCConnectRunner:
    def __init__(self, backend: hpc_connect.Backend) -> None:
        self.backend = backend

    def execute(self, batch: "TestBatch") -> int | None:
        raise NotImplementedError
        
    def rc_environ(self, batch: "TestBatch") -> dict[str, str | None]:
        variables: dict[str, str | None] = dict(batch.variables)
        variables.update({"CANARY_LEVEL": "1", "CANARY_DISABLE_KB": "1"})
        if canary.config.get("debug"):
            variables["CANARY_DEBUG"] = "on"
        f = batch.workspace.joinpath("config.json")
        with open(f, "w") as fh:
            canary.config.dump(fh)
        variables[canary.config.CONFIG_ENV_FILENAME] = str(f)
        return variables

    def nodes_required(self, batch: "TestBatch") -> int:
        """Nodes required to run cases in ``batch``"""
        max_count_per_type: dict[str, int] = {}
        for case in batch.cases:
            reqd_resources = case.required_resources()
            total_slots_per_type: dict[str, int] = {}
            for member in reqd_resources:
                type = member["type"]
                total_slots_per_type[type] = total_slots_per_type.get(type, 0) + member["slots"]
            for type, count in total_slots_per_type.items():
                max_count_per_type[type] = max(max_count_per_type.get(type, 0), count)
        node_count: int = 1
        for type, count in max_count_per_type.items():
            try:
                count_per_node: int = self.backend.count_per_node(type)
            except ValueError:
                continue
            if count_per_node > 0:
                node_count = max(node_count, int(math.ceil(count / count_per_node)))
        return node_count

    def scheduler_args(self) -> list[str]:
        options: list[str] = []
        if args := canary.config.getoption("canary_hpc_scheduler_args"):
            options.extend(args)
        return options

    @contextmanager
    def handle_signals(
        self, cancellables: list[Cancellable], batch: "TestBatch"
    ) -> Generator[None, None, None]:
        def cancel(signum, frame):
            logger.warning(f"Cancelling batch {batch} due to captured signal {signum!r}")
            try:
                for c in cancellables:
                    try:
                        c.cancel()
                    except Exception as e:
                        logger.debug(f"Failed to cancel {c}", exc_info=e)
            finally:
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)

        current = {}
        for signum in (signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT, signal.SIGTERM):
            current[signum] = signal.getsignal(signum)
            signal.signal(signum, cancel)
        try:
            yield
        except:
            for signum, handler in current.items():
                signal.signal(signum, handler)


class HPCConnectBatchRunner(HPCConnectRunner):
    def execute(self, batch: "TestBatch") -> int | None:
        logger.debug(f"Starting {batch} on pid {os.getpid()}")
        with batch.workspace.enter():
            future = self.submit(batch)
            with self.handle_signals([future], batch):
                rc = future.result()
        rc = future.result()
        logger.debug(f"Finished {batch} with exit code {rc}")
        return rc

    def submit(self, batch: "TestBatch") -> hpc_connect.futures.Future:
        variables = self.rc_environ(batch)
        invocation = self.canary_invocation(batch)
        job = hpc_connect.JobSpec(
            name=f"canary.{batch.id[:7]}",
            commands=[invocation],
            nodes=self.nodes_required(batch),
            time_limit=batch.estimated_runtime() * batch.timeout_multiplier,
            env=variables,
            output=str(batch.workspace.joinpath(batch.stdout)),
            error=str(batch.workspace.joinpath(batch.stdout)),
            workspace=batch.workspace.dir,
            submit_args=self.scheduler_args(),
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
        args: list[str] = [sys.executable, "-m", "canary", *default_args, "hpc", "exec"]
        n = canary.config.getoption("canary_hpc_batch_workers") or -1
        args.extend(
            [
                f"--workers={n}",
                f"--backend={self.backend.name}",
                f"--workspace={batch.workspace.dir}",
            ]
        )
        return shlex.join(args)


class HPCConnectSeriesRunner(HPCConnectRunner):
    def execute(self, batch: "TestBatch") -> int | None:
        logger.debug(f"Starting {batch} on pid {os.getpid()}")
        rc: int = -1
        with batch.workspace.enter():
            futures: list[hpc_connect.futures.Future] = []
            for case in batch.cases:
                future = self.submit(batch, case)
                futures.append(future)
            with self.handle_signals(futures, batch):
                for future in hpc_connect.futures.as_completed(futures):
                    rc = max(rc, future.result())
        logger.debug(f"Finished {batch} with exit code {rc}")
        return rc

    def submit(self, batch: "TestBatch", case: "canary.TestCase") -> hpc_connect.futures.Future:
        variables = self.rc_environ(batch)
        timeoutx = batch.timeout_multiplier
        invocation = self.canary_invocation(batch, case)
        job = hpc_connect.JobSpec(
            name=f"canary.{case.id[:7]}",
            commands=[invocation],
            cpus=case.cpus,
            gpus=case.gpus,
            time_limit=case.runtime * timeoutx,
            env=variables,
            output=str(batch.workspace.joinpath(f"{case.id[:7]}-out.txt")),
            error=str(batch.workspace.joinpath(f"{case.id[:7]}-err.txt")),
            workspace=batch.workspace.dir,
            submit_args=self.scheduler_args(),
        )
        future = self.backend.submission_manager().submit(job, exclusive=False)
        return future

    def canary_invocation(self, batch: "TestBatch", case: "canary.TestCase") -> str:
        """Write the canary invocation used to run this test case"""
        default_args = [sys.executable, "-m", "canary", "-C", str(batch.workspace.dir)]
        if canary.config.get("debug"):
            default_args.append("-d")
        default_args.extend(["hpc", "exec"])
        args = [
            *default_args,
            f"--backend={self.backend.name}",
            f"--case={case.id}",
            f"--workspace={batch.workspace.dir}",
        ]
        invocation = shlex.join(args)
        return invocation
