# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import math
import os
import shlex
import signal
import sys
import time
from contextlib import contextmanager
from itertools import repeat
from typing import TYPE_CHECKING
from typing import Generator

import hpc_connect

import canary

if TYPE_CHECKING:
    from .batchspec import TestBatch


logger = canary.get_logger(__name__)


class HPCConnectRunner:
    def __init__(self, backend: hpc_connect.HPCSubmissionManager) -> None:
        self.backend = backend

    def execute(self, batch: "TestBatch") -> int | None:
        logger.debug(f"Starting {batch} on pid {os.getpid()}")
        with batch.workspace.enter():
            proc = self.submit(batch)
            if getattr(proc, "jobid", None) not in (None, "none", "<none>"):
                batch.jobid = proc.jobid
            with self.handle_signals(proc, batch):
                while True:
                    try:
                        if proc.poll() is not None:
                            break
                    except Exception:
                        logger.exception("Batch @*b{%s}: polling job failed!" % batch.id[:7])
                        break
                    time.sleep(self.backend.polling_frequency)
        return getattr(proc, "returncode", None)

    def submit(self, batch: "TestBatch") -> hpc_connect.HPCProcess:
        raise NotImplementedError

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
                count_per_node: int = self.backend.config.count_per_node(type)
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
        self, proc: hpc_connect.HPCProcess, batch: "TestBatch"
    ) -> Generator[None, None, None]:
        def cancel(signum, frame):
            logger.warning(f"Cancelling batch {batch} due to captured signal {signum!r}")
            try:
                proc.cancel()
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
    def submit(self, batch: "TestBatch") -> hpc_connect.HPCProcess:
        variables: dict[str, str | None] = dict(batch.variables)
        variables.update({"CANARY_LEVEL": "1", "CANARY_DISABLE_KB": "1"})
        if canary.config.get("debug"):
            variables["CANARY_DEBUG"] = "on"
        invocation = self.canary_invocation(batch)
        proc = self.backend.submit(
            f"canary.{batch.id[:7]}",
            [invocation],
            nodes=self.nodes_required(batch),
            scriptname=str(batch.workspace.joinpath(batch.script)),
            output=str(batch.workspace.joinpath(batch.stdout)),
            error=str(batch.workspace.joinpath(batch.stdout)),
            submit_flags=self.scheduler_args(),
            variables=variables,
            qtime=batch.qtime() * batch.timeout_multiplier,
        )
        return proc

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
    def submit(self, batch: "TestBatch") -> hpc_connect.HPCProcess:
        variables: dict[str, str | None] = dict(batch.variables)
        variables.update({"CANARY_LEVEL": "1", "CANARY_DISABLE_KB": "1"})
        if canary.config.get("debug"):
            variables["CANARY_DEBUG"] = "on"
        timeoutx = batch.timeout_multiplier
        invocations = self.canary_invocation(batch)
        proc = self.backend.submitn(
            [case.id for case in batch.cases],
            [[invocation] for invocation in invocations],
            cpus=[case.cpus for case in batch.cases],
            gpus=[case.gpus for case in batch.cases],
            scriptname=[str(batch.workspace.joinpath(f"{case.id}-inp.sh")) for case in batch.cases],
            output=[str(batch.workspace.joinpath(f"{case.id}-out.txt")) for case in batch.cases],
            error=[str(batch.workspace.joinpath(f"{case.id}-err.txt")) for case in batch.cases],
            submit_flags=list(repeat(self.scheduler_args(), len(batch.cases))),
            variables=list(repeat(variables, len(batch.cases))),
            qtime=[case.runtime * timeoutx for case in batch.cases],
        )
        return proc

    def canary_invocation(self, batch: "TestBatch") -> list[str]:
        """Write the canary invocation used to run this test case"""
        default_args = [sys.executable, "-m", "canary", "-C", str(batch.workspace.dir)]
        if canary.config.get("debug"):
            default_args.append("-d")
        default_args.extend(["hpc", "exec"])
        invocations: list[str] = []
        for case in batch.cases:
            args = [
                *default_args,
                f"--backend={self.backend.name}",
                f"--case={case.id}",
                f"--workspace={batch.workspace.dir}",
            ]
            invocations.append(shlex.join(args))
        return invocations
