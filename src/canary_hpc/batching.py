# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import math
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
from _canary.atc import AbstractTestCase
from _canary.status import Status
from _canary.util import cpu_count
from _canary.util.hash import hashit
from _canary.util.time import time_in_seconds

from . import binpack

logger = canary.get_logger(__name__)


class TestBatch(AbstractTestCase):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch

    """

    def __init__(self, cases: Sequence[canary.TestCase], runtime: float | None = None) -> None:
        super().__init__()
        self.validate(cases)
        self.cases = list(cases)
        self.session = self.cases[0].session
        self._id = hashit(",".join(case.id for case in self.cases), length=20)
        self.total_duration: float = -1
        self._runtime: float
        if runtime is None:
            self._runtime = self.find_approximate_runtime()
        elif canary.config.getoption("canary_hpc_batch_timeout_strategy") == "conservative":
            self._runtime = max(runtime, self.find_approximate_runtime())
        else:
            self._runtime = runtime
        self._status: Status
        self._jobid: str | None = None
        for case in self.cases:
            if any(dep not in self.cases for dep in case.dependencies):
                self._status = Status("PENDING")
                break
        else:
            self._status = Status("READY")

    def __iter__(self):
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)

    def __repr__(self) -> str:
        case_repr: str
        if len(self.cases) <= 3:
            case_repr = ",".join(repr(case) for case in self.cases)
        else:
            case_repr = f"{self.cases[0]!r},{self.cases[1]!r},...,{self.cases[-1]!r}"
        return f"TestBatch({case_repr})"

    @property
    def variables(self) -> dict[str, str | None]:
        return {"CANARY_BATCH_ID": str(self.id)}

    @property
    def runtime(self) -> float:
        return self._runtime

    def find_approximate_runtime(self) -> float:
        if len(self.cases) == 1:
            return self.cases[0].runtime
        _, height = packed_perimeter(self.cases)
        t = sum(c.runtime for c in self)
        return float(min(height, t))

    @cached_property
    def timeout_multiplier(self) -> float:
        timeoutx: float = canary.config.get("config:timeout:multiplier") or 1.0
        timeouts = canary.config.getoption("timeout") or {}
        if t := timeouts.get("multiplier"):
            timeoutx = float(t)
        return timeoutx

    @property
    def timeout(self) -> float:
        return self.qtime() * self.timeout_multiplier

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

    def size(self) -> float:
        vec = [self.runtime, self.cpus, self.gpus]
        return math.sqrt(sum(_**2 for _ in vec))

    def required_resources(self) -> list[list[dict[str, Any]]]:
        group: list[dict[str, Any]] = [{"type": "cpus", "slots": 1} for _ in range(self.cpus)]
        # by default, only one resource group is returned
        return [group]

    @property
    def duration(self):
        start = min(case.start for case in self)
        stop = max(case.stop for case in self)
        if start == -1 or stop == -1:
            return -1
        return stop - start

    def validate(self, cases: Sequence[canary.TestCase]):
        errors = 0
        for case in cases:
            if case.mask:
                logger.critical(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.mask:
                    errors += 1
                    logger.critical(f"{dep}: dependent of {case} is masked")
        if errors:
            raise ValueError("Stopping due to previous errors")

    def command(self, stage: str = "run") -> list[str]:
        raise NotImplementedError

    @property
    def cputime(self) -> float:
        return sum(case.cpus * min(case.runtime, 5.0) for case in self) * 1.5

    @property
    def has_dependencies(self) -> bool:
        return any(case.dependencies for case in self.cases)

    @property
    def cpus(self) -> int:
        return 1  # only one CPU needed to submit this batch and wait for scheduler

    @property
    def gpus(self) -> int:
        return 0  # no GPU needed to submit this batch and wait for scheduler

    @property
    def jobid(self) -> str | None:
        return self._jobid

    @jobid.setter
    def jobid(self, arg: str) -> None:
        self._jobid = arg

    @property
    def status(self) -> Status:
        if self._status.name == "PENDING":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            pending = 0
            for case in self.cases:
                for dep in case.dependencies:
                    if dep.status.name in ("PENDING", "READY", "RUNNING"):
                        pending += 1
            if not pending:
                self._status.set("READY")
        return self._status

    @status.setter
    def status(self, arg: Status | dict[str, str]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg)
        else:
            self._status.set(arg["name"], message=arg["message"])

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    def reload_and_check(self) -> list[canary.TestCase]:
        self.refresh()
        failed: list[canary.TestCase] = []
        for case in self:
            if case.status.name == "RUNNING":
                # Job was cancelled
                case.status.set("CANCELLED", f"batch {self.id[:7]} cancelled")
            elif case.status.name == "SKIPPED":
                pass
            elif case.status.name == "READY":
                case.status.set("NOT_RUN", "test not run for unknown reasons")
            elif case.timekeeper.start_on != "NA" and case.timekeeper.finished_on == "NA":
                case.status.set("CANCELLED", "test case cancelled")
            if not case.status.name in ("SKIPPED", "SUCCESS"):
                failed.append(case)
                logger.debug(f"Batch {self}: test case failed: {case}")
        return failed

    @property
    def id(self) -> str:
        return self._id

    def submission_script_filename(self) -> Path:
        return self.stage(self.id) / "canary-inp.sh"

    @staticmethod
    def logfile(batch_id: str) -> Path:
        """Get the path of the batch log file"""
        return TestBatch.stage(batch_id) / "canary-out.txt"

    @property
    def path(self) -> Path:
        return Path(".canary/work/canary_hpc/batches", self.id[:2], self.id[2:])

    @property
    def working_directory(self) -> str:
        return self.stage(self.id)

    def _combined_status(self) -> str:
        """Return a string like

        1 success, 2 fail, 3 timeout

        """
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.name] = stat.get(case.status.name, 0) + 1
        colors = Status.colors
        parts: list[str] = []
        for name, n in stat.items():
            color = Status.defaults[name][1][0]
            parts.append("@%s{%d %s}" % (color, n, name))
        return ", ".join(parts)

    def format(self, format_spec: str) -> str:
        replacements: dict[str, str] = {
            "%id": self.id[:7],
            "%p": str(self.path),
            "%P": str(self.stage(self.id)),
            "%n": repr(self),
            "%j": self.jobid or "none",
            "%l": str(len(self)),
            "%S": self._combined_status(),
            "%s.n": self.status.cname,
            "%s.v": self.status.name,
            "%s.d": self.status.message or "unknown",
        }
        if canary.config.getoption("format", "short") == "long":
            replacements["%X"] = replacements["%p"]
        else:
            replacements["%X"] = replacements["%n"]
        formatted_text = format_spec
        for placeholder, value in replacements.items():
            formatted_text = formatted_text.replace(placeholder, value)
        return formatted_text.strip()

    def times(self) -> tuple[float | None, float | None, float | None]:
        """Return total, running, and time in queue"""
        duration: float | None = self.total_duration if self.total_duration > 0 else None
        running: float | None = None
        time_in_queue: float | None = None
        if any(_.start > 0 for _ in self.cases) and any(_.stop > 0 for _ in self.cases):
            ti = min(_.start for _ in self.cases if _.start > 0)
            tf = max(_.stop for _ in self.cases if _.stop > 0)
            running = tf - ti
            if duration:
                time_in_queue = max(duration - (tf - ti), 0)
        return duration, running, time_in_queue

    @staticmethod
    def loadconfig(batch_id: str) -> dict[str, Any]:
        file = TestBatch.configfile(batch_id)
        return json.loads(file.read_text())

    @staticmethod
    def configfile(batch_id: str) -> Path:
        return TestBatch.stage(batch_id) / "config.json"

    @staticmethod
    def stage(batch_id: str) -> Path:
        root = canary_hpc_stage() / "batches" / batch_id[:2]
        if (root / batch_id[2:]).exists():
            return root / batch_id[2:]
        for match in root.glob(f"{batch_id[2:]}*"):
            return match
        return root / batch_id[2:]

    @staticmethod
    def find(batch_id: str) -> str:
        """Find the full batch ID from batch_id"""
        stage = canary_hpc_stage()
        for match in stage.glob(f"batches/{batch_id[:2]}/{batch_id[2:]}*"):
            return "".join([match.parent.stem, match.stem])
        raise BatchNotFound(f"cannot find stage for batch {batch_id}")

    def setup(self) -> None:
        file = self.configfile(self.id)
        file.parent.mkdir(parents=True, exist_ok=True)
        config = {"session": self.session, "cases": [case.id for case in self]}
        file.write_text(json.dumps(config, indent=2))

    def run(  # type: ignore[override]
        self, backend: hpc_connect.HPCSubmissionManager, qsize: int = 1, qrank: int = 1
    ) -> None:
        def cancel(sig, frame):
            nonlocal proc
            logger.info(f"Cancelling run due to captured signal {sig!r}")
            if proc is not None:
                logger.info("Cancelling hpc-connect process")
                proc.cancel()
            if sig == signal.SIGINT:
                raise KeyboardInterrupt
            elif sig == signal.SIGTERM:
                os._exit(1)

        logger.debug(f"Running batch {self.id[:7]}")
        start = time.monotonic()
        variables = dict(self.variables)
        variables["CANARY_LEVEL"] = "1"
        variables["CANARY_DISABLE_KB"] = "1"
        if canary.config.get("config:debug"):
            variables["CANARY_DEBUG"] = "on"

        batchspec = canary.config.getoption("canary_hpc_batchspec")
        flat = batchspec["layout"] == "flat"
        timeoutx = self.timeout_multiplier
        try:
            breadcrumb = self.stage(self.id) / ".running"
            breadcrumb.touch()
            default_int_signal = signal.signal(signal.SIGINT, cancel)
            default_term_signal = signal.signal(signal.SIGTERM, cancel)
            proc: hpc_connect.HPCProcess | None = None
            logger.debug(f"Submitting batch {self.id}")
            workspace = canary.Workspace.load()
            default_args: list[str] = ["-C", str(workspace.root.parent)]
            if canary.config.get("config:debug"):
                default_args.append("-d")
            if backend.supports_subscheduling and flat:
                submit_script = self.submission_script_filename()
                scriptdir = submit_script.parent
                variables.pop("CANARY_BATCH_ID", None)
                proc = backend.submitn(
                    [case.id for case in self],
                    [
                        [self.canary_testcase_invocation(case, backend, default_args)]
                        for case in self
                    ],
                    cpus=[case.cpus for case in self],
                    gpus=[case.gpus for case in self],
                    scriptname=[str(scriptdir / f"{case.id}-inp.sh") for case in self],
                    output=[str(scriptdir / f"{case.id}-out.txt") for case in self],
                    error=[str(scriptdir / f"{case.id}-err.txt") for case in self],
                    submit_flags=list(repeat(get_scheduler_args(), len(self))),
                    variables=list(repeat(variables, len(self))),
                    qtime=[case.runtime * timeoutx for case in self],
                )
            else:
                qtime = self.qtime() * timeoutx
                nodes = self.nodes_required(backend)
                proc = backend.submit(
                    f"canary.{self.id[:7]}",
                    [self.canary_batch_invocation(backend, default_args)],
                    nodes=nodes,
                    scriptname=str(self.submission_script_filename()),
                    output=str(self.logfile(self.id)),
                    error=str(self.logfile(self.id)),
                    submit_flags=get_scheduler_args(),
                    variables=variables,
                    qtime=qtime,
                )
            assert proc is not None
            if getattr(proc, "jobid", None) not in (None, "none", "<none>"):
                self.jobid = proc.jobid
            while True:
                try:
                    if proc.poll() is not None:
                        break
                except Exception as e:
                    logger.exception(self.format("Batch @*b{%id}: polling job failed!"))
                    break
                time.sleep(backend.polling_frequency)
        finally:
            breadcrumb.unlink()
            signal.signal(signal.SIGINT, default_int_signal)
            signal.signal(signal.SIGTERM, default_term_signal)
            self.total_duration = time.monotonic() - start
            self.refresh()
            if all([_.status.name in ("READY", "PENDING") for _ in self.cases]):
                f = "Batch @*b{%id}: no test cases have started; check %P for any emitted scheduler log files."
                logger.warning(self.format(f))
            for case in self.cases:
                if case.status.name == "SKIPPED":
                    pass
                elif case.status.name == "RUNNING":
                    logger.debug(f"{case}: cancelling (status: running)")
                    case.status.set("CANCELLED", "case failed to stop")
                    case.save()
                elif case.timekeeper.started_on != "NA" and case.timekeeper.finished_on == "NA":
                    logger.debug(f"{case}: cancelling (status: {case.status})")
                    case.status.set("CANCELLED", "case failed to stop")
                    case.save()
                elif case.status.name == "READY":
                    logger.debug(f"{case}: case failed to start")
                    case.status.set("NOT_RUN", f"case failed to start (batch: {self.id})")
                    case.save()
            if rc := getattr(proc, "returncode", None):
                logger.debug(
                    self.format(f"Batch @*b{{%id}}: batch processing exited with code {rc}")
                )

        return

    def finish(self) -> None:
        pass

    @lru_cache
    def nodes_required(self, backend: hpc_connect.HPCSubmissionManager) -> int:
        """Nodes required to run cases in ``batch``"""
        max_count_per_type: dict[str, int] = {}
        for case in self:
            reqd_resources = case.required_resources()
            total_slots_per_type: dict[str, int] = {}
            for group in reqd_resources:
                for member in group:
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
        args.extend(["hpc", "exec", f"--backend={backend.name}", f"--case={case.id}", self.id])
        return shlex.join(args)

    def canary_batch_invocation(
        self, backend: hpc_connect.HPCSubmissionManager, default_args: list[str]
    ) -> str:
        """Write the canary invocation used to run this batch."""
        args: list[str] = ["canary"]
        args.extend(default_args)
        workers = canary.config.getoption("canary_hpc_batch_workers") or -1
        args.extend(["hpc", "exec", f"--workers={workers}", f"--backend={backend.name}", self.id])
        return shlex.join(args)


def canary_hpc_stage() -> Path:
    workspace = canary.Workspace.load()
    return workspace.cache_dir / "canary_hpc"


def get_scheduler_args() -> list[str]:
    options: list[str] = []
    if args := canary.config.getoption("canary_hpc_scheduler_args"):
        options.extend(args)
    return options


def batch_testcases(
    *,
    cases: list["canary.TestCase"],
    nodes: Literal["any", "same"] = "any",
    layout: Literal["flat", "atomic"] = "flat",
    count: int | None = None,
    duration: float | None = None,
    width: int | None = None,
    cpus_per_node: int | None = None,
) -> list[TestBatch]:
    if duration is None and count is None:
        duration = 30 * 60  # 30 minute default
    elif duration is not None and count is not None:
        raise ValueError("duration and count are mutually exclusive")

    bins: list[binpack.Bin] = []

    grouper: binpack.GrouperType | None = None
    if nodes == "same":
        grouper = GroupByNodes(cpus_per_node=cpus_per_node)
    # The binpacking code works with Block not TestCase.
    blocks: dict[str, binpack.Block] = {}
    map: dict[str, canary.TestCase] = {}
    graph: dict[canary.TestCase, list[canary.TestCase]] = {}
    for case in cases:
        graph[case] = [dep for dep in case.dependencies if dep in cases]
    ts = TopologicalSorter(graph)
    ts.prepare()
    while ts.is_active():
        ready = ts.get_ready()
        for case in ready:
            map[case.id] = case
            dependencies: list[binpack.Block] = [blocks[dep.id] for dep in case.dependencies]
            blocks[case.id] = binpack.Block(
                case.id, case.cpus, math.ceil(case.runtime), dependencies=dependencies
            )
        ts.done(*ready)
    if duration is not None:
        height = math.ceil(float(duration))
        logger.debug(f"Batching test cases using duration={height}")
        bins = binpack.pack_to_height(
            list(blocks.values()), height=height, width=width, grouper=grouper
        )
    else:
        assert isinstance(count, int)
        logger.debug(f"Batching test cases using count={count}")
        if layout == "atomic":
            bins = binpack.pack_by_count_atomic(list(blocks.values()), count)
        else:
            bins = binpack.pack_by_count(list(blocks.values()), count, grouper=grouper)
    return [TestBatch([map[block.id] for block in bin]) for bin in bins]


def packed_perimeter(
    cases: Iterable[canary.TestCase], cpus_per_node: int | None = None
) -> tuple[int, int]:
    cpus_per_node = cpus_per_node or cpu_count()
    cases = sorted(cases, key=lambda c: c.size(), reverse=True)
    cpus = max(case.cpus for case in cases)
    nodes = math.ceil(cpus / cpus_per_node)
    width = nodes * cpus_per_node
    blocks: list[binpack.Block] = []
    for case in cases:
        blocks.append(binpack.Block(case.id, case.cpus, math.ceil(case.runtime)))
    packer = binpack.Packer()
    packer.pack(blocks, width=width)
    return binpack.perimeter(blocks)


class GroupByNodes:
    def __init__(self, cpus_per_node: int | None) -> None:
        self.cpus_per_node: int = cpus_per_node or cpu_count()

    def __call__(self, blocks: list[binpack.Block]) -> list[list[binpack.Block]]:
        groups: dict[int, list[binpack.Block]] = {}
        for block in blocks:
            nodes_reqd = math.ceil(block.width / self.cpus_per_node)
            groups.setdefault(nodes_reqd, []).append(block)
        return list(groups.values())


class BatchNotFound(Exception):
    pass
