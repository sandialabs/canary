# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from _canary.timekeeper import Timekeeper
from .batchspec import BatchSpec
import copy
import datetime
import json
import math
import multiprocessing as mp
import os
import shlex
import signal
import time
from functools import cached_property
from functools import lru_cache
from graphlib import TopologicalSorter
from itertools import repeat
from pathlib import Path
from typing import Any
from typing import Iterable
from typing import Literal
from typing import Sequence

import hpc_connect

import canary
from _canary.status import Status
from _canary.testcase import Measurements
from _canary.util import cpu_count
from _canary.util.hash import hashit
from _canary.util.time import time_in_seconds

from . import binpack

logger = canary.get_logger(__name__)


class BatchStatus:
    def __init__(self, children: Iterable[canary.TestCase]) -> None:
        self._children: list[canary.TestCase] = list(children)
        self.base_status: Status
        for child in self._children:
            if any(dep not in self._children for dep in child.dependencies):
                self.base_status = Status.PENDING()
                break
        else:
            self.base_status = Status.READY()

    @property
    def name(self) -> str:
        return self.base_status.name

    @property
    def cname(self) -> str:
        return self.base_status.cname

    @property
    def color(self) -> str:
        return self.base_status.color

    def asdict(self) -> dict:
        return self.base_status.asdict()

    def set(
        self,
        status: str | int | Status,
        message: str | None = None,
        code: int | None = None,
        propagate: bool = True,
    ) -> None:
        self.base_status.set(status, message=message, code=code)
        if propagate:
            for child in self._children:
                if child.status.name in ("READY", "PENDING"):
                    child.status.set("NOT_RUN")
                elif child.status.name == "RUNNING":
                    child.timekeeper.stop()
                    child.status.set("CANCELLED")
                else:
                    child.status.set(status, message=message, code=code)

    @property
    def status(self) -> Status:
        return self.base_status


class TestBatch:
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch

    """

    def __init__(self, spec: BatchSpec, workspace: Path) -> None:
        super().__init__()
        self.spec = spec
        self.cases = spec.cases
        self.session = self.spec.session
        workspace = self.cases[0].workspace
        self.workspace = workspace.root / f"canary-hpc/batches/{self.id[:2]}/{self.id[2:]}"
        self.configfile = self.workspace / "config.json"
        self.script = "canary-inp.sh"
        self.stdout = "canary-out.txt"
        self.runtime: float = self.find_approximate_runtime()
        self._status: BatchStatus = BatchStatus(self.cases)
        self._resources: dict[str, list[dict]] = {}

        self.jobid: str | None = None
        self.variables = {"CANARY_BATCH_ID": str(self.spec.id)}
        self.exclusive = False
        self.measurements = Measurements()
        self.timekeeper = Timekeeper()

    def __iter__(self):
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)

    def __str__(self) -> str:
        if self.status.name in ("READY", "PENDING"):
            return f"{type(self).__name__}({len(self)} {self.status.cname})"
        combined_stat = self._combined_status()
        return f"{type(self).__name__}({combined_stat})"

    def __repr__(self) -> str:
        case_repr: str
        if len(self.cases) <= 3:
            case_repr = ",".join(repr(case) for case in self.cases)
        else:
            case_repr = f"{self.cases[0]!r},{self.cases[1]!r},...,{self.cases[-1]!r}"
        return f"TestBatch({case_repr})"

    def cost(self) -> float:
        cpus = max(case.cpus for case in self.cases)
        return math.sqrt(cpus**2 + self.runtime**2)

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
        scheduler_args = get_scheduler_args()
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
        if self._status.name == "PENDING":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            pending = 0
            for case in self.cases:
                for dep in case.dependencies:
                    if dep.status.name in ("PENDING", "READY", "RUNNING"):
                        pending += 1
            if not pending:
                self._status.set("READY", propagate=False)
        return self._status

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def path(self) -> Path:
        return Path(".canary/work/canary_hpc/batches", self.id[:2], self.id[2:])

    def _combined_status(self) -> str:
        """Return a string like

        1 success, 2 fail, 3 timeout

        """
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.name] = stat.get(case.status.name, 0) + 1
        parts: list[str] = []
        for name, n in stat.items():
            color = Status.defaults[name][1][0]
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
            if duration:
                time_in_queue = max(duration - running, 0)
        return duration, running, time_in_queue

    @staticmethod
    def loadconfig(workspace: str) -> dict[str, Any]:
        file = Path(workspace) / "config.json"
        return json.loads(file.read_text())

    @staticmethod
    def find(batch_id: str) -> str:
        """Find the full batch ID from batch_id"""
        sessions_dir = canary_hpc_sessions()
        for match in sessions_dir.rglob(f"canary-hpc/batches/{batch_id[:2]}/{batch_id[2:]}*"):
            return "".join([match.parent.stem, match.stem])
        raise BatchNotFound(f"cannot find workspace for batch {batch_id}")

    def setup(self) -> None:
        self.configfile.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "id": self.id,
            "session": self.session,
            "workspace": str(self.workspace),
            "cases": [case.id for case in self],
            "status": self.status.asdict(),
            "timekeeper": self.timekeeper.asdict(),
        }
        self.configfile.write_text(json.dumps(config, indent=2))

    def run(self, queue: mp.Queue, backend: hpc_connect.HPCSubmissionManager) -> None:
        logger.debug(f"Running batch {self.id[:7]}")
        start = time.monotonic()
        variables = dict(self.variables)
        variables["CANARY_LEVEL"] = "1"
        variables["CANARY_DISABLE_KB"] = "1"
        if canary.config.get("debug"):
            variables["CANARY_DEBUG"] = "on"

        batchspec = canary.config.getoption("canary_hpc_batchspec")
        flat = batchspec["layout"] == "flat"
        timeoutx = self.timeout_multiplier
        try:
            breadcrumb = self.workspace / ".running"
            breadcrumb.touch()
            proc: hpc_connect.HPCProcess | None = None
            logger.debug(f"Submitting batch {self.id[:7]}")
            workspace = canary.Workspace.load()
            default_args: list[str] = ["-C", str(workspace.root.parent)]
            if canary.config.get("debug"):
                default_args.append("-d")
            with self.timekeeper.timeit():
                if backend.supports_subscheduling and flat:
                    variables.pop("CANARY_BATCH_ID", None)
                    proc = backend.submitn(
                        [case.id for case in self],
                        [
                            [self.canary_testcase_invocation(case, backend, default_args)]
                            for case in self
                        ],
                        cpus=[case.cpus for case in self],
                        gpus=[case.gpus for case in self],
                        scriptname=[str(self.workspace / f"{case.id}-inp.sh") for case in self],
                        output=[str(self.workspace / f"{case.id}-out.txt") for case in self],
                        error=[str(self.workspace / f"{case.id}-err.txt") for case in self],
                        submit_flags=list(repeat(get_scheduler_args(), len(self))),
                        variables=list(repeat(variables, len(self))),
                        qtime=[case.runtime * timeoutx for case in self],
                    )
                else:
                    invocation = self.canary_batch_invocation(backend, default_args)
                    nodes = self.nodes_required(backend)
                    proc = backend.submit(
                        f"canary.{self.id[:7]}",
                        [invocation],
                        nodes=nodes,
                        scriptname=str(self.workspace / self.script),
                        output=str(self.workspace / self.stdout),
                        error=str(self.workspace / self.stdout),
                        submit_flags=get_scheduler_args(),
                        variables=variables,
                        qtime=self.qtime() * timeoutx,
                    )
                assert proc is not None
                install_handlers(proc, self)
                if getattr(proc, "jobid", None) not in (None, "none", "<none>"):
                    self.jobid = proc.jobid
                while True:
                    try:
                        if proc.poll() is not None:
                            break
                    except Exception as e:
                        logger.exception("Batch @*b{%%s}: polling job failed!" % self.id[:7])
                        break
                    time.sleep(backend.polling_frequency)
        finally:
            breadcrumb.unlink(missing_ok=True)
            uninstall_handlers()
            self.refresh()
            stat = "SUCCESS" if all(case.status == "SUCCESS" for case in self) else "FAILED"
            self.status.set(stat, propagate=False)
            data: dict[str, Any] = {}
            data[self.id] =  {"status": self.status.status, "timekeeper": self.timekeeper}
            for case in self.cases:
                if case.status.name in ("PENDING", "READY"):
                    case.status.set("NOT_RUN")
                elif case.status.name == "RUNNING":
                    case.status.set("CANCELLED")
                data[case.id] = {"status": case.status, "timekeeper": case.timekeeper}
            queue.put(data)
            if rc := getattr(proc, "returncode", None):
                logger.debug("Batch @*b{%s}: batch exited with code %d" % (self.id[:7], rc))

        return

    def on_result(self, data: dict[str, Any]):
        """Update my state.  This is the companion of queue.put

        Called by the resource queue executor with the results put into the multiprocessing queue
        after a run

        """
        if mydata := data.pop(self.id, None):
            if stat := mydata.get("status"):
                self.status.set(stat.name, stat.message, stat.code, propagate=False)
            if timekeeper := mydata.get("timekeeper"):
                self.timekeeper.started_on = timekeeper.started_on
                self.timekeeper.finished_on = timekeeper.finished_on
                self.timekeeper.duration = timekeeper.duration
        for case in self.cases:
            if d := data.get(case.id):
                case.on_result(d)

    def finish(self) -> None:
        pass

    def save(self):
        cfg = self.loadconfig(self.workspace)
        cfg["status"] = self.status.asdict()
        with open(self.configfile, "w") as fh:
            json.dump(cfg, fh, indent=2)
        for case in self:
            case.save()

    @lru_cache
    def nodes_required(self, backend: hpc_connect.HPCSubmissionManager) -> int:
        """Nodes required to run cases in ``batch``"""
        max_count_per_type: dict[str, int] = {}
        for case in self:
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
                count_per_node: int = backend.config.count_per_node(type)
            except ValueError:
                continue
            if count_per_node > 0:
                node_count = max(node_count, int(math.ceil(count / count_per_node)))
        return node_count

    def canary_testcase_invocation(
        self,
        case: canary.TestCase,
        backend: hpc_connect.HPCSubmissionManager,
        default_args: list[str],
    ) -> str:
        """Write the canary invocation used to run this test case"""
        args: list[str] = ["canary"]
        args.extend(default_args)
        args.extend(["hpc", "exec", f"--backend={backend.name}", f"--case={case.id}", f"--workspace={self.workspace}"])
        return shlex.join(args)

    def canary_batch_invocation(
        self, backend: hpc_connect.HPCSubmissionManager, default_args: list[str]
    ) -> str:
        """Write the canary invocation used to run this batch."""
        args: list[str] = ["canary"]
        args.extend(default_args)
        workers = canary.config.getoption("canary_hpc_batch_workers") or -1
        args.extend(["hpc", "exec", f"--workers={workers}", f"--backend={backend.name}", f"--workspace={self.workspace}"])
        return shlex.join(args)


def canary_hpc_sessions() -> Path:
    workspace = canary.Workspace.load()
    return workspace.sessions_dir


def get_scheduler_args() -> list[str]:
    options: list[str] = []
    if args := canary.config.getoption("canary_hpc_scheduler_args"):
        options.extend(args)
    return options


def install_handlers(proc: hpc_connect.HPCProcess, batch: TestBatch) -> None:
    def cancel(signum, frame):
        logger.warning(f"Cancelling batch {batch} due to captured signal {signum!r}")
        try:
            proc.cancel()
        finally:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

    signal.signal(signal.SIGUSR1, cancel)
    signal.signal(signal.SIGUSR2, cancel)
    signal.signal(signal.SIGINT, cancel)
    signal.signal(signal.SIGTERM, cancel)


def uninstall_handlers() -> None:
    signal.signal(signal.SIGUSR1, signal.SIG_DFL)
    signal.signal(signal.SIGUSR2, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)


class BatchNotFound(Exception):
    pass
