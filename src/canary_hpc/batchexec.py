# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import json
import math
import os
import shlex
import signal
import sys
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol
from typing import Sequence

import hpc_connect
import hpc_connect.futures

import canary
from _canary.util.multiprocessing import SimpleQueue

if TYPE_CHECKING:
    from .batchspec import TestBatch


logger = canary.get_logger(__name__)


class Cancellable(Protocol):
    def cancel(self) -> bool: ...


class HPCConnectRunner:
    def __init__(self, backend: hpc_connect.Backend) -> None:
        self.backend = backend

    def execute(self, batch: "TestBatch", queue: SimpleQueue) -> int | None:
        raise NotImplementedError

    def rc_environ(self, batch: "TestBatch") -> dict[str, str | None]:
        variables: dict[str, str | None] = dict(batch.variables)
        level = int(os.getenv("CANARY_LEVEL", "0"))
        variables.update(
            {
                "CANARY_LEVEL": str(level + 1),
                "CANARY_DISABLE_KB": "1",
                "CANARY_LIVE": "0",
                "CANARY_HPC_BATCH": str(batch.spec.id),
            }
        )
        if canary.config.get("debug"):
            variables["CANARY_DEBUG"] = "on"
        f = batch.workspace.joinpath("config.json")
        with open(f, "w") as fh:
            canary.config.dump(fh)
        variables[canary.config.CONFIG_ENV_FILENAME] = str(f)
        return variables

    def scheduler_args(self) -> list[str]:
        options: list[str] = []
        if args := canary.config.getoption("canary_hpc_scheduler_args"):
            options.extend(args)
        return options

    @contextmanager
    def handle_signals(self, targets: Sequence[Cancellable], batch: "TestBatch"):
        def cancel(signum, frame):
            logger.warning(f"Cancelling batch {batch} due to captured signal {signum!r}")
            try:
                for target in targets:
                    try:
                        target.cancel()
                    except Exception as e:
                        logger.debug(f"Failed to cancel {target}", exc_info=e)
            finally:
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)

        current = {}
        for signum in (signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT, signal.SIGTERM):
            current[signum] = signal.getsignal(signum)
            signal.signal(signum, cancel)
        try:
            yield
        finally:
            for signum, handler in current.items():
                signal.signal(signum, handler)

    def _cancel_future(self, future: Cancellable, why: str) -> None:
        try:
            ok = future.cancel()
        except Exception as e:
            logger.debug("Future cancel failed (%s): %s", why, e)
        else:
            logger.warning("Cancelled future (%s). cancel() returned %s", why, ok)

    def generate_resource_pool(self, batch: "TestBatch") -> None:
        node_count = self.nodes_required(batch)
        resources: dict[str, list[Any]] = {}
        additional_properties = {"node_count": node_count, "backend": self.backend.name}
        for type in self.backend.resource_types():
            count = self.backend.count_per_node(type)
            slots = 1
            if not type.endswith("s"):
                type += "s"
            resources[type] = [{"id": str(j), "slots": slots} for j in range(count * node_count)]
            additional_properties[f"{type}_per_node"] = count
        pool: dict[str, Any] = {
            "resources": resources,
            "additional_properties": additional_properties,
        }
        f = batch.workspace.joinpath("resource_pool.json")
        f.write_text(json.dumps({"resource_pool": pool}, indent=2))

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


class HPCConnectBatchRunner(HPCConnectRunner):
    def execute(self, batch: "TestBatch", queue: SimpleQueue) -> int | None:
        started_at: float = -1.0

        def set_starttime(future: hpc_connect.futures.Future):
            nonlocal started_at
            started_at = time.time()
            batch.timekeeper.started = started_at
            queue.put({"event": "STARTED", "timestamp": started_at})

        def set_jobid(future: hpc_connect.futures.Future):
            batch.jobid = future.jobid

        logger.debug(f"Starting {batch} on pid {os.getpid()}")
        self.generate_resource_pool(batch)

        submitted_at = batch.timekeeper.submitted if batch.timekeeper.submitted > 0 else time.time()
        queue_deadline = submitted_at + batch.queue_timeout

        run_timeout = float(batch.timeout * batch.timeout_multiplier)

        with batch.workspace.enter():
            future = self.submit(batch)
            future.add_jobstart_callback(set_starttime)
            future.add_jobid_callback(set_jobid)

            with self.handle_signals([future], batch):
                poll = max(1.0, getattr(future, "_polling_interval", 1.0))

                while True:
                    # Done?
                    if future.done():
                        rc = future.result()
                        logger.debug(f"Finished {batch} with exit code {rc}")
                        return rc

                    now = time.time()

                    # Queue timeout (waiting for scheduler start)
                    if started_at < 0.0:
                        if now >= queue_deadline:
                            future.cancel()
                            raise TimeoutError(
                                f"Batch {batch.id[:7]} exceeded queue timeout "
                                f"{batch.queue_timeout:.1f}s"
                            )
                        time.sleep(poll)
                        continue

                    # Run timeout (after job start)
                    remaining = (started_at + run_timeout) - now
                    if remaining <= 0:
                        future.cancel()
                        raise TimeoutError(
                            f"Batch {batch.id[:7]} exceeded run timeout {run_timeout:.1f}s"
                        )

                    # Block up to remaining time (or poll interval), whichever is smaller
                    try:
                        rc = future.result(timeout=min(poll, remaining))
                    except TimeoutError:
                        continue
                    else:
                        logger.debug(f"Finished {batch} with exit code {rc}")
                        return rc

    def submit(self, batch: "TestBatch") -> hpc_connect.futures.Future:
        variables = self.rc_environ(batch)
        invocation = self.canary_invocation(batch)
        node_count = self.nodes_required(batch)
        variables["CANARY_HPC_NODE_COUNT"] = str(node_count)
        job = hpc_connect.JobSpec(
            name=f"canary.{batch.id[:7]}",
            commands=[invocation],
            nodes=node_count,
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
        gpu_backend = canary.config.getoption("gpu_backend")
        if gpu_backend not in (None, "auto"):
            default_args.append(f"--gpu-backend={gpu_backend}")
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
    def execute(self, batch: "TestBatch", queue: SimpleQueue) -> int | None:
        started_at: float = -1.0

        def set_starttime(future: hpc_connect.futures.Future):
            nonlocal started_at
            started_at = time.time()
            batch.timekeeper.started = started_at
            queue.put({"event": "STARTED", "timestamp": started_at})

        logger.debug(f"Starting {batch} on pid {os.getpid()}")
        self.generate_resource_pool(batch)

        # TestBatch.run() already set submitted and emitted SUBMITTED
        submitted_at = batch.timekeeper.submitted if batch.timekeeper.submitted > 0 else time.time()
        queue_deadline = submitted_at + batch.queue_timeout

        # Overall run timeout once the first job actually starts
        run_timeout = float(batch.timeout * batch.timeout_multiplier)

        rc: int = -1
        with batch.workspace.enter():
            futures: list[hpc_connect.futures.Future] = []
            for i, case in enumerate(batch.cases):
                future = self.submit(batch, case)
                if i == 0:
                    future.add_jobstart_callback(set_starttime)
                futures.append(future)

            with self.handle_signals(futures, batch):
                poll = max(1.0, max(getattr(f, "_polling_interval", 1.0) for f in futures))

                # --- queue timeout: wait for first scheduler start ---
                while started_at < 0.0:
                    if time.time() >= queue_deadline:
                        for f in futures:
                            try:
                                f.cancel()
                            except Exception:  # nosec B110
                                pass
                        raise TimeoutError(
                            f"Batch {batch.id[:7]} exceeded queue timeout "
                            f"{batch.queue_timeout:.1f}s"
                        )
                    # If everything finishes without ever "starting", treat as done
                    if all(f.done() for f in futures):
                        for f in futures:
                            try:
                                rc = max(rc, f.result())
                            except Exception:
                                rc = max(rc, 1)
                        logger.debug(f"Finished {batch} with exit code {rc}")
                        return rc
                    time.sleep(poll)

                # --- run timeout: from first STARTED until all complete ---
                try:
                    for f in hpc_connect.futures.as_completed(
                        futures,
                        timeout=run_timeout,
                        polling_interval=poll,
                        cancel_on_exception=True,
                    ):
                        rc = max(rc, f.result())
                except TimeoutError:
                    # as_completed already cancels remaining futures on timeout
                    raise TimeoutError(
                        f"Batch {batch.id[:7]} exceeded run timeout {run_timeout:.1f}s"
                    )

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
        default_args = [
            sys.executable,
            "-m",
            "canary",
            "-C",
            str(batch.workspace.dir),
            "-r",
            f"cpus={case.cpus}",
            "-r",
            f"gpus={case.gpus}",
        ]
        if canary.config.get("debug"):
            default_args.append("-d")
        gpu_backend = canary.config.getoption("gpu_backend")
        if gpu_backend not in (None, "auto"):
            default_args.append(f"--gpu-backend={gpu_backend}")
        default_args.extend(["hpc", "exec"])
        args = [
            *default_args,
            "--workers=1",
            f"--backend={self.backend.name}",
            f"--case={case.id}",
            f"--workspace={batch.workspace.dir}",
        ]
        invocation = shlex.join(args)
        return invocation
