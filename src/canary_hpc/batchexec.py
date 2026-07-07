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
from _canary.util import json_helper
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
        resource_pool_file = batch.workspace.joinpath("resource_pool.json")
        resource_pool_data = json.loads(resource_pool_file.read_text())["resource_pool"]
        snapshot = canary.config.snapshot()
        snapshot["resource_manager"] = {"resource_pool": resource_pool_data}
        f = batch.workspace.joinpath("config.json")
        with open(f, "w") as fh:
            fh.write(json_helper.dumps(snapshot, indent=2))
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

        additional_properties: dict[str, Any] = {
            "node_count": node_count,
            "backend": self.backend.name,
            "source": "hpc-batch",
        }

        resource_types = {
            _canonical_resource_type(rtype) for rtype in self.backend.resource_types()
        }
        resource_types.update({"cpus", "gpus"})

        nodes: list[dict[str, Any]] = []

        for i in range(node_count):
            resources: dict[str, list[dict[str, Any]]] = {}

            for rtype in sorted(resource_types):
                try:
                    count = self.backend.count_per_node(rtype)
                except ValueError:
                    try:
                        count = self.backend.count_per_node(_singular_resource_type(rtype))
                    except ValueError:
                        count = 0

                resources[rtype] = _resource_specs(count, rtype=rtype)
                additional_properties[f"{rtype}_per_node"] = count

            nodes.append({"id": str(i), "resources": resources})

        pool: dict[str, Any] = {
            "allow_multinode": node_count > 1,
            "additional_properties": additional_properties,
            "nodes": nodes,
        }

        f = batch.workspace.joinpath("resource_pool.json")
        f.write_text(json.dumps({"resource_pool": pool}, indent=2))

    def nodes_required(self, batch: "TestBatch") -> int:
        """Return number of scheduler nodes required to run jobs in batch."""
        max_count_per_type: dict[str, int] = {}
        explicit_nodes = 1

        for job in batch.jobs:
            reqd_resources = job.required_resources()
            total_slots_per_type: dict[str, int] = {}

            for member in reqd_resources:
                rtype = member["type"]
                slots = int(member["slots"])

                if rtype in ("node", "nodes"):
                    explicit_nodes = max(explicit_nodes, slots)
                    continue

                rtype = _canonical_resource_type(rtype)
                total_slots_per_type[rtype] = total_slots_per_type.get(rtype, 0) + slots

            for rtype, count in total_slots_per_type.items():
                max_count_per_type[rtype] = max(max_count_per_type.get(rtype, 0), count)

        node_count = explicit_nodes

        for rtype, count in max_count_per_type.items():
            try:
                count_per_node = self.backend.count_per_node(rtype)
            except ValueError:
                try:
                    count_per_node = self.backend.count_per_node(_singular_resource_type(rtype))
                except ValueError:
                    continue

            if count_per_node > 0:
                node_count = max(node_count, int(math.ceil(count / count_per_node)))

        return node_count


def _canonical_resource_type(rtype: str) -> str:
    return rtype if rtype.endswith("s") else f"{rtype}s"


def _singular_resource_type(rtype: str) -> str:
    return rtype[:-1] if rtype.endswith("s") else rtype


def _resource_specs(count: int, *, rtype: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    for j in range(count):
        spec: dict[str, Any] = {"id": str(j), "slots": 1}

        if rtype == "gpus":
            spec["properties"] = {"vendor": "UNKNOWN"}

        specs.append(spec)

    return specs


class HPCConnectBatchRunner(HPCConnectRunner):
    def execute(self, batch: "TestBatch", queue: SimpleQueue) -> int | None:
        started_at: float = -1.0

        def set_starttime(future: hpc_connect.futures.Future):
            nonlocal started_at
            started_at = time.time()
            batch.timekeeper.started = started_at
            queue.put({"event": "job_started", "timestamp": started_at})

        def set_jobid(future: hpc_connect.futures.Future):
            jobid = batch.jobid = future.jobid
            queue.put({"event": "job_updated", "timestamp": time.time(), "attrs": {"jobid": jobid}})

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
        hpc_job = hpc_connect.JobSpec(
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
        if all(b.jobid is not None for b in batch.dependencies):
            hpc_job = hpc_job.with_dependencies([b.jobid for b in batch.dependencies])  # type: ignore
        try:
            future = self.backend.submission_manager().submit(hpc_job)
        except Exception:
            logger.exception(f"Submission for job {hpc_job} failed")
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
            queue.put({"event": "job_started", "timestamp": started_at})

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
            for i, job in enumerate(batch.jobs):
                future = self.submit(batch, job)
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

    def submit(self, batch: "TestBatch", job: "canary.Job") -> hpc_connect.futures.Future:
        variables = self.rc_environ(batch)
        timeoutx = batch.timeout_multiplier
        invocation = self.canary_invocation(batch, job)
        hpc_job = hpc_connect.JobSpec(
            name=f"canary.{job.id[:7]}",
            commands=[invocation],
            cpus=job.cpus,
            gpus=job.gpus,
            time_limit=job.runtime * timeoutx,
            env=variables,
            output=str(batch.workspace.joinpath(f"{job.id[:7]}-out.txt")),
            error=str(batch.workspace.joinpath(f"{job.id[:7]}-err.txt")),
            workspace=batch.workspace.dir,
            submit_args=self.scheduler_args(),
        )
        future = self.backend.submission_manager().submit(hpc_job, exclusive=False)
        return future

    def canary_invocation(self, batch: "TestBatch", job: "canary.Job") -> str:
        """Write the canary invocation used to run this job"""
        default_args = [
            sys.executable,
            "-m",
            "canary",
            "-C",
            str(batch.workspace.dir),
            "-r",
            f"cpus={job.cpus}",
            "-r",
            f"gpus={job.gpus}",
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
            f"--job={job.id}",
            f"--workspace={batch.workspace.dir}",
        ]
        invocation = shlex.join(args)
        return invocation
