# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import copy
import dataclasses
import datetime
import json
import math
import time
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

import hpc_connect

import canary
from _canary.job import BaseJob
from _canary.job import JobPhase
from _canary.job import JobState
from _canary.status import Status
from _canary.testexec import ExecutionSpace
from _canary.util.multiprocessing import SimpleQueue
from _canary.util.serialize import serialize
from _canary.util.time import time_in_seconds

from .status import BatchStatus

if TYPE_CHECKING:
    from .batchexec import HPCConnectRunner

logger = canary.get_logger(__name__)


@dataclasses.dataclass
class BatchSpec:
    layout: str
    jobs: list[canary.Job]
    dependencies: list["BatchSpec"] = dataclasses.field(default_factory=list)
    id: str = dataclasses.field(init=False)
    session: str = dataclasses.field(init=False)
    rparameters: dict[str, int] = dataclasses.field(init=False)
    exclusive: bool = dataclasses.field(init=False, default=False)

    def __post_init__(self) -> None:
        import uuid

        self.id = str(uuid.uuid4())  # hashit(",".join(job.id for job in self.jobs), length=20)
        self.session = cast(str, self.jobs[0].workspace.session)
        # 1 CPU and not GPUs needed to submit this batch and wait for scheduler
        self.rparameters = {"cpus": 1, "gpus": 0}

    def __len__(self) -> int:
        return len(self.jobs)

    def required_resources(self) -> list[dict[str, Any]]:
        return [{"type": "cpus", "slots": 1}]


class TestBatch(BaseJob):
    """A batch of jobs

    Args:
      jobs: The list of jobs in this batch

    """

    def __init__(
        self,
        spec: BatchSpec,
        workspace: ExecutionSpace,
        dependencies: list["TestBatch"] | None = None,
        backend_supports_dependencies: bool = False,
    ) -> None:
        super().__init__()
        self.spec = spec
        self.jobs = spec.jobs
        self.status: BatchStatus = BatchStatus(self.jobs)
        self.session = self.spec.session
        self.workspace = workspace
        self.lockfile = self.workspace.joinpath("batch.lock")
        self.script = "canary-inp.sh"
        self.stdout = "canary-out.txt"
        self.runtime: float = self.find_approximate_runtime()
        self.state = JobState()
        self._allocation: dict[str, dict] = {"metadata": {}, "resources": {}}
        self.jobid: str | None = None
        self.variables = {"CANARY_BATCH_ID": str(self.spec.id)}
        self.dependencies: list["TestBatch"] = dependencies or []
        self.backend_supports_dependencies = backend_supports_dependencies

    def __iter__(self):
        return iter(self.jobs)

    def __len__(self) -> int:
        return len(self.jobs)

    def __str__(self) -> str:
        p = [f"id={self.id[:7]}"]
        if self.jobid:
            p.append(f"jobid={self.jobid}")
        return f"TestBatch({','.join(p)})"

    def __repr__(self) -> str:
        job_repr: str
        if len(self.jobs) <= 3:
            job_repr = ",".join(repr(job) for job in self.jobs)
        else:
            job_repr = f"{self.jobs[0]!r},{self.jobs[1]!r},...,{self.jobs[-1]!r}"
        return f"TestBatch({job_repr})"

    @property
    def id(self) -> str:
        return self.spec.id

    def display_name(self, **kwargs: Any) -> str:
        name = str(self)
        if not kwargs.get("status"):
            return name
        if self.state.is_running() or self.state.is_pending():
            return f"{name} ({len(self)} {self.state.phase.value})"
        else:
            combined_stat = self._combined_status()
            return f"{name} ({combined_stat})"

    def cost(self) -> float:
        cpus = max(job.cpus for job in self.jobs)
        return math.sqrt(cpus**2 + self.runtime**2)

    @property
    def cpus(self) -> int:
        return self.spec.rparameters["cpus"]

    @property
    def gpus(self) -> int:
        return self.spec.rparameters["gpus"]

    @property
    def cpu_ids(self) -> list[str]:
        return [str(_["id"]) for _ in self.resources.get("cpus", [])]

    @property
    def gpu_ids(self) -> list[str]:
        return [str(_["id"]) for _ in self.resources.get("gpus", [])]

    def find_approximate_runtime(self) -> float:
        from .batching import packed_perimeter

        if len(self.jobs) == 1:
            return self.jobs[0].runtime
        _, height = packed_perimeter(self.jobs)
        t = sum(c.runtime for c in self)
        return float(min(height, t))

    @cached_property
    def timeout_multiplier(self) -> float:
        if cli_timeouts := canary.config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                return float(t)
        elif t := canary.config.get("run:timeout:multiplier"):
            return float(t)
        return 1.0

    @property
    def timeout(self) -> float:
        return self.estimated_runtime()

    @property
    def queue_timeout(self) -> float:
        four_hours = 4.0 * 60.0 * 60.0
        return canary.config.getoption("hpc_queue_timeout") or four_hours

    def total_timeout(self) -> float:
        return self.queue_timeout + self.timeout_multiplier * self.timeout

    def estimated_runtime(self) -> float:
        if scheduler_args := canary.config.getoption("hpc_scheduler_args"):
            p = argparse.ArgumentParser()
            p.add_argument("--time", "--time-limit", dest="qtime")
            a, _ = p.parse_known_args(scheduler_args)
            if a.qtime:
                return time_in_seconds(a.qtime)
        if len(self.jobs) == 1:
            return self.jobs[0].runtime
        total_runtime = self.runtime
        if total_runtime < 100.0:
            total_runtime = 300.0
        elif total_runtime < 300.0:
            total_runtime = 600.0
        elif total_runtime < 600.0:
            total_runtime = 1200.0
        elif total_runtime < 1800.0:
            total_runtime = 2400.0
        elif total_runtime < 3600.0:
            total_runtime = 5000.0
        else:
            total_runtime *= 1.25
        return total_runtime

    @property
    def resources(self) -> dict[str, list[dict]]:
        """resources is of the form::

          resources[type] = [{"id": str, "slots": int}]

        If the test required 2 cpus and 2 gpus, resources would look like::

          resources = {
              "cpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}],
              "gpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}],
          }

        """
        return self._allocation["resources"]

    @property
    def allocation(self) -> dict[str, dict]:
        return self._allocation

    def assign_resources(self, arg: dict[str, dict]) -> None:
        self._allocation.clear()
        self._allocation.update(copy.deepcopy(arg))

    def free_resources(self) -> dict[str, dict]:
        tmp = copy.deepcopy(self._allocation)
        self._allocation.clear()
        self._allocation.update({"metadata": {}, "resources": {}})
        return tmp

    def required_resources(self) -> list[dict[str, Any]]:
        return self.spec.required_resources()

    def dependency_batches_submitted(self) -> bool:
        return all(d.jobid is not None for d in self.dependencies)

    def dependency_batches_complete(self) -> bool:
        return all(all(c.state.is_done() for c in d.jobs) for d in self.dependencies)

    def refresh_readiness(self) -> None:
        # If we're already done/running, nothing to do.
        if self.state.is_done() or self.state.is_running():
            return
        # If backend supports deps, batch becomes "ready" once deps are submitted (or complete).
        # Otherwise must wait for deps complete.
        if not self.dependencies:
            return  # ready immediately
        if self.backend_supports_dependencies:
            # ready to submit when dependencies have jobids OR are complete
            if self.dependency_batches_submitted() or self.dependency_batches_complete():
                return
        else:
            # no backend deps => must wait for complete
            if self.dependency_batches_complete():
                return
        # not ready yet; remain pending
        return

    def is_runnable(self) -> bool:
        if self.state.is_done():
            return False
        if self.status.is_skipped():
            return False
        # Nothing else makes a batch permanently unrunnable today
        return True

    def is_ready(self) -> bool:
        if self.state.is_done() or self.state.is_running():
            return False
        if not self.is_runnable():
            return False
        if not self.dependencies:
            return True
        if self.backend_supports_dependencies:
            return self.dependency_batches_submitted() or self.dependency_batches_complete()
        else:
            return self.dependency_batches_complete()

    def run(self, backend: hpc_connect.Backend, queue: SimpleQueue) -> None:

        logger.debug(f"Running batch {self.id[:7]}")
        runner: "HPCConnectRunner" = canary.config.pluginmanager.hook.canary_hpc_batch_runner(
            backend=backend, batch=self
        )

        rc: int | None = -1
        try:
            hpc_connect.config.export()
            logger.debug(f"Submitting batch {self.id[:7]}")
            queue.put({"event": "job_submitted", "timestamp": time.time()})
            self.timekeeper.submitted = time.time()
            try:
                rc = runner.execute(self, queue=queue)
            finally:
                self.timekeeper.finished = time.time()
        except Exception:
            logger.exception(f"Failed to run batch {self}")
            rc = 1
        finally:
            if rc is None:
                rc = 1
            self.refresh()
            self.state.phase = JobPhase.DONE
            if all(job.status.is_success() for job in self):
                self.status.set_base(outcome="SUCCESS")
            else:
                self.status.set_base(outcome="FAILED", reason="One or more jobs did not pass")
            logger.debug(
                "Batch [bold blue]%s[/]: batch exited with code %s" % (self.id[:7], str(rc))
            )

        return

    def getstate(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        data[self.id] = {
            "status": self.status.base,
            "timekeeper": self.timekeeper,
            "state": self.state,
        }
        for job in self.jobs:
            if job.state.is_pending():
                job.status = Status.BROKEN(reason=f"{job.state=} after execution of batch")
            elif job.state.is_running():
                job.status = Status.CANCELLED(reason=f"{job.state=} after execution of batch")
            data[job.id] = {"status": job.status, "timekeeper": job.timekeeper, "state": job.state}
        return data

    def setstate(self, data: dict[str, Any]):
        """Update my state.

        Called by the resource queue executor with the results put into the multiprocessing queue
        after a run

        """
        if mydata := data.pop(self.id, None):
            if stat := mydata.get("status"):
                self.status.set_base(
                    category=stat.category, outcome=stat.outcome, reason=stat.reason, code=stat.code
                )
            if st := mydata.get("state"):
                self.state.phase = st.phase
            if timekeeper := mydata.get("timekeeper"):
                self.timekeeper.submitted = timekeeper.submitted
                self.timekeeper.started = timekeeper.started
                self.timekeeper.finished = timekeeper.finished
        for job in self.jobs:
            if d := data.get(job.id):
                job.setstate(d)
        self.save()

    def finish(self) -> None:
        pass

    def refresh(self) -> None:
        for job in self:
            job.refresh()

    def _combined_status(self) -> str:
        """Return a string like

        1 success, 2 fail, 3 timeout

        """
        stat: dict[str, int] = {}
        for job in self.jobs:
            stat[job.status.category] = stat.get(job.status.category, 0) + 1
        parts: list[str] = []
        for name, n in stat.items():
            parts.append("%d %s" % (n, name))
        return ", ".join(parts)

    def times(self) -> tuple[float | None, float | None, float | None]:
        """Return total, running, and time in queue"""

        def started(job):
            t = job.timekeeper.started
            return None if t < 0 else datetime.datetime.fromtimestamp(t)

        def finished(job):
            t = job.timekeeper.finished
            return None if t < 0 else datetime.datetime.fromtimestamp(t)

        total_duration = self.timekeeper.duration()
        duration: float | None = total_duration if total_duration > 0 else None
        running: float | None = None
        time_in_queue: float | None = None
        started_on = [started(job) for job in self.jobs]
        finished_on = [finished(job) for job in self.jobs]
        if any(started_on) and any(finished_on):
            ti = min(dt for dt in started_on if dt)
            tf = max(dt for dt in finished_on if dt)
            running = (tf - ti).total_seconds()
            if duration is not None and running is not None:
                time_in_queue = max(duration - running, 0)
        return duration, running, time_in_queue

    @staticmethod
    def loadconfig(workspace: str) -> dict[str, Any]:
        file = Path(workspace) / "batch.lock"
        return json.loads(file.read_text())

    def setup(self) -> None:
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "id": self.id,
            "session": self.session,
            "workspace": str(self.workspace.dir),
            "jobs": [job.id for job in self],
            "status": serialize(self.status)["base"],
            "timekeeper": serialize(self.timekeeper),
            "measurements": serialize(self.measurements),
            "allocation": serialize(self.allocation),
        }
        self.lockfile.write_text(json.dumps(config, indent=2))
        return

    def save(self):
        cfg = json.loads(self.lockfile.read_text())
        cfg["status"] = serialize(self.status)["base"]
        cfg["timekeeper"] = serialize(self.timekeeper)
        cfg["measurements"] = serialize(self.measurements)
        cfg["allocation"] = serialize(self.allocation)
        with open(self.lockfile, "w") as fh:
            json.dump(cfg, fh, indent=2)
        for job in self:
            job.save()

    def set_status(
        self,
        category: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
        code: int = -1,
    ) -> None:
        # apply to the batch’s base status
        self.status.set_base(category=category, outcome=outcome, reason=reason, code=code)
