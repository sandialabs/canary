# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import argparse
import copy
import dataclasses
import datetime
import json
import math
import multiprocessing as mp
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

import hpc_connect

import canary
from _canary.status import Status
from _canary.testcase import Measurements
from _canary.testexec import ExecutionSpace
from _canary.timekeeper import Timekeeper
from _canary.util.hash import hashit
from _canary.util.time import time_in_seconds

from .status import BatchStatus

if TYPE_CHECKING:
    from .batchexec import HPCConnectRunner

logger = canary.get_logger(__name__)


@dataclasses.dataclass
class BatchSpec:
    layout: str
    cases: list[canary.TestCase]
    id: str = dataclasses.field(init=False)
    session: str = dataclasses.field(init=False)
    rparameters: dict[str, int] = dataclasses.field(init=False)
    exclusive: bool = dataclasses.field(init=False, default=False)

    def __post_init__(self) -> None:
        self.id = hashit(",".join(case.id for case in self.cases), length=20)
        self.session = cast(str, self.cases[0].workspace.session)
        # 1 CPU and not GPUs needed to submit this batch and wait for scheduler
        self.rparameters = {"cpus": 1, "gpus": 0}

    def __len__(self) -> int:
        return len(self.cases)

    def required_resources(self) -> list[dict[str, Any]]:
        return [{"type": "cpus", "slots": 1}]


class TestBatch:
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch

    """

    def __init__(self, spec: BatchSpec, workspace: ExecutionSpace) -> None:
        super().__init__()
        self.spec = spec
        self.cases = spec.cases
        self.session = self.spec.session
        self.workspace = workspace
        self.lockfile = self.workspace.joinpath("batch.lock")
        self.script = "canary-inp.sh"
        self.stdout = "canary-out.txt"
        self.runtime: float = self.find_approximate_runtime()
        self._status: BatchStatus = BatchStatus(self.cases)
        self._resources: dict[str, list[dict]] = {}

        self.jobid: str | None = None
        self.id = self.spec.id
        self.variables = {"CANARY_BATCH_ID": str(self.spec.id), "CANARY_LEVEL": "1"}
        self.exclusive = False
        self.measurements = Measurements()
        self.timekeeper = Timekeeper()

    def __iter__(self):
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)

    def __str__(self) -> str:
        return f"batch[id={self.id[:8]}]"

    def __repr__(self) -> str:
        case_repr: str
        if len(self.cases) <= 3:
            case_repr = ",".join(repr(case) for case in self.cases)
        else:
            case_repr = f"{self.cases[0]!r},{self.cases[1]!r},...,{self.cases[-1]!r}"
        return f"TestBatch({case_repr})"

    def display_name(self, **kwargs: Any) -> str:
        name = str(self)
        if not kwargs.get("status"):
            return name
        if self.status.category in ("READY", "PENDING"):
            return f"{name} ({len(self)} {self.status.cname})"
        else:
            combined_stat = self._combined_status()
            return f"{name} ({combined_stat})"

    def cost(self) -> float:
        cpus = max(case.cpus for case in self.cases)
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

        if len(self.cases) == 1:
            return self.cases[0].runtime
        _, height = packed_perimeter(self.cases)
        t = sum(c.runtime for c in self)
        return float(min(height, t))

    @cached_property
    def timeout_multiplier(self) -> float:
        if cli_timeouts := canary.config.getoption("timeout"):
            if t := cli_timeouts.get("multiplier"):
                return float(t)
        elif t := canary.config.get("timeout:multiplier"):
            return float(t)
        return 1.0

    @property
    def timeout(self) -> float:
        return self.qtime()

    def qtime(self) -> float:
        if scheduler_args := canary.config.getoption("canary_hpc_scheduler_args"):
            p = argparse.ArgumentParser()
            p.add_argument("--time", dest="qtime")
            a, _ = p.parse_known_args(scheduler_args)
            if a.qtime:
                return time_in_seconds(a.qtime)
        if len(self.cases) == 1:
            return self.cases[0].runtime
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
        """resources is of the form

        resources[type] = [{"id": str, "slots": int}]

        If the test required 2 cpus and 2 gpus, resources would look like

        resources = {
            "cpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}],
            "gpus": [{"id": "1", "slots": 1}, {"id": "2", "slots": 1}],
        }

        """
        return self._resources

    def assign_resources(self, arg: dict[str, list[dict]]) -> None:
        self._resources.clear()
        self._resources.update(arg)

    def free_resources(self) -> dict[str, list[dict]]:
        tmp = copy.deepcopy(self._resources)
        self._resources.clear()
        return tmp

    def required_resources(self) -> list[dict[str, Any]]:
        return self.spec.required_resources()

    @property
    def status(self) -> BatchStatus:
        if self._status.category == "PENDING":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            pending = 0
            for case in self.cases:
                for dep in case.dependencies:
                    if dep.status.category in ("PENDING", "READY", "RUNNING"):
                        pending += 1
            if not pending:
                self._status.set("READY", propagate=False)
        return self._status

    def set_status(
        self,
        status: str | int | Status,
        reason: str | None = None,
        code: int | None = None,
    ) -> None:
        self.status.set(status, reason=reason, code=code)

    def run(self, queue: mp.Queue, backend: hpc_connect.HPCSubmissionManager) -> None:
        logger.debug(f"Running batch {self.id[:8]}")
        runner: "HPCConnectRunner" = canary.config.pluginmanager.hook.canary_hpc_batch_runner(
            backend=backend, batch=self
        )
        rc: int | None = -1
        try:
            logger.debug(f"Submitting batch {self.id[:8]}")
            with self.timekeeper.timeit():
                rc = runner.execute(self)
        except Exception:
            rc = 1
        finally:
            if rc is None:
                rc = 1
            self.refresh()
            stat = "SUCCESS" if all(case.status == "SUCCESS" for case in self) else "FAILED"
            self.status.set(stat, propagate=False)
            data: dict[str, Any] = {}
            data[self.id] = {"status": self.status.status, "timekeeper": self.timekeeper}
            for case in self.cases:
                if case.status.category in ("PENDING", "READY"):
                    case.status.set("BROKEN")
                elif case.status.category == "RUNNING":
                    case.status.set("CANCELLED")
                data[case.id] = {"status": case.status, "timekeeper": case.timekeeper}
            queue.put(data)
            logger.debug("Batch @*b{%s}: batch exited with code %s" % (self.id[:8], str(rc)))

        return

    def on_result(self, data: dict[str, Any]):
        """Update my state.  This is the companion of queue.put

        Called by the resource queue executor with the results put into the multiprocessing queue
        after a run

        """
        if mydata := data.pop(self.id, None):
            if stat := mydata.get("status"):
                self.status.set(
                    stat.category,
                    reason=stat.reason,
                    code=stat.code,
                    kind=stat.kind,
                    propagate=False,
                )
            if timekeeper := mydata.get("timekeeper"):
                self.timekeeper.started_on = timekeeper.started_on
                self.timekeeper.finished_on = timekeeper.finished_on
                self.timekeeper.duration = timekeeper.duration
        for case in self.cases:
            if d := data.get(case.id):
                case.on_result(d)
        self.save()

    def finish(self) -> None:
        pass

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    def _combined_status(self) -> str:
        """Return a string like

        1 success, 2 fail, 3 timeout

        """
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.category] = stat.get(case.status.category, 0) + 1
        parts: list[str] = []
        for name, n in stat.items():
            color = Status.categories[name][1][0]
            parts.append("@%s{%d %s}" % (color, n, name))
        return ", ".join(parts)

    def times(self) -> tuple[float | None, float | None, float | None]:
        """Return total, running, and time in queue"""

        def started(case):
            s = case.timekeeper.started_on
            return None if s == "NA" else datetime.datetime.fromisoformat(s)

        def finished(case):
            f = case.timekeeper.finished_on
            return None if f == "NA" else datetime.datetime.fromisoformat(f)

        total_duration = self.timekeeper.duration
        duration: float | None = total_duration if total_duration > 0 else None
        running: float | None = None
        time_in_queue: float | None = None
        started_on = [started(case) for case in self.cases]
        finished_on = [finished(case) for case in self.cases]
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
            "cases": [case.id for case in self],
            "status": self.status.asdict(),
            "timekeeper": self.timekeeper.asdict(),
            "measurements": self.measurements.asdict(),
        }
        self.lockfile.write_text(json.dumps(config, indent=2))

    def save(self):
        cfg = json.loads(self.lockfile.read_text())
        cfg["status"] = self.status.asdict()
        cfg["timekeeper"] = self.timekeeper.asdict()
        cfg["measurements"] = self.measurements.asdict()
        with open(self.lockfile, "w") as fh:
            json.dump(cfg, fh, indent=2)
        for case in self:
            case.save()
