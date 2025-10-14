# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import glob
import json
import math
import os
import shlex
import signal
import time
from functools import lru_cache
from itertools import repeat
from typing import Any
from typing import Sequence

import hpc_connect

import canary
from _canary.atc import AbstractTestCase
from _canary.status import Status
from _canary.util.hash import hashit
from _canary.util.time import time_in_seconds

logger = canary.get_logger(__name__)


class TestBatch(AbstractTestCase):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch

    """

    def __init__(
        self,
        cases: Sequence[canary.TestCase],
        runtime: float | None = None,
    ) -> None:
        super().__init__()
        self.validate(cases)
        self.cases = list(cases)
        self._id = hashit(",".join(case.id for case in self.cases), length=20)
        self.total_duration: float = -1
        self._submit_cpus = 1
        self._submit_gpus = 0
        self.max_cpus_required = max([case.cpus for case in self.cases])
        self.max_gpus_required = max([case.gpus for case in self.cases])
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
                self._status = Status("pending")
                break
        else:
            self._status = Status("ready")

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
        from .partitioning import packed_perimeter

        if len(self.cases) == 1:
            return self.cases[0].runtime
        _, height = packed_perimeter(self.cases)
        t = sum(c.runtime for c in self)
        return float(min(height, t))

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
            if case.masked():
                logger.critical(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.masked():
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
        return self._submit_cpus

    @property
    def gpus(self) -> int:
        return self._submit_gpus

    @gpus.setter
    def gpus(self, arg: int) -> None:
        self._gpus = arg

    @property
    def jobid(self) -> str | None:
        return self._jobid

    @jobid.setter
    def jobid(self, arg: str) -> None:
        self._jobid = arg

    @property
    def status(self) -> Status:
        if self._status.value == "pending":
            # Determine if dependent cases have completed and, if so, flip status to 'ready'
            pending = 0
            for case in self.cases:
                for dep in case.dependencies:
                    if dep.status.value in ("created", "pending", "ready", "running"):
                        pending += 1
            if not pending:
                self._status.set("ready")
        return self._status

    @status.setter
    def status(self, arg: Status | dict[str, str]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg["value"], details=arg["details"])

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    @property
    def id(self) -> str:
        return self._id

    def submission_script_filename(self) -> str:
        return os.path.join(self.stage(self.id), "canary-inp.sh")

    @staticmethod
    def logfile(batch_id: str) -> str:
        """Get the path of the batch log file"""
        return os.path.join(TestBatch.stage(batch_id), "canary-out.txt")

    @property
    def path(self) -> str:
        return os.path.join(".canary/batches", self.id[:2], self.id[2:])

    @property
    def working_directory(self) -> str:
        return self.path

    def save(self):
        f = os.path.join(self.stage(self.id), "index")
        canary.filesystem.mkdirp(os.path.dirname(f))
        with open(f, "w") as fh:
            json.dump([case.id for case in self], fh, indent=2)

    def _combined_status(self) -> str:
        """Return a string like

        1 success, 2 fail, 3 timeout

        """
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        colors = Status.colors
        return ", ".join("@%s{%d %s}" % (colors[v], n, v) for (v, n) in stat.items())

    def format(self, format_spec: str) -> str:
        replacements: dict[str, str] = {
            "%id": self.id[:7],
            "%p": self.path,
            "%P": self.stage(self.id),
            "%n": repr(self),
            "%j": self.jobid or "none",
            "%l": str(len(self)),
            "%S": self._combined_status(),
            "%s.n": self.status.cname,
            "%s.v": self.status.value,
            "%s.d": self.status.details or "unknown",
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
    def loadindex(batch_id: str) -> list[str]:
        full_batch_id = TestBatch.find(batch_id)
        stage = TestBatch.stage(full_batch_id)
        f = os.path.join(stage, "index")
        if not os.path.exists(f):
            raise ValueError(f"Index for batch {batch_id} not found in {stage}")
        with open(f, "r") as fh:
            return json.load(fh)

    @staticmethod
    def stage(batch_id: str) -> str:
        work_tree = canary.config.get("session:work_tree")
        assert work_tree is not None
        root = os.path.join(work_tree, ".canary/batches", batch_id[:2])
        if os.path.exists(root) and os.path.exists(os.path.join(root, batch_id[2:])):
            return os.path.join(root, batch_id[2:])
        pattern = os.path.join(root, f"{batch_id[2:]}*")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
        return os.path.join(root, batch_id[2:])

    @staticmethod
    def find(batch_id: str) -> str:
        """Find the full batch ID from batch_id"""
        work_tree = canary.config.get("session:work_tree")
        assert work_tree is not None
        pattern = os.path.join(work_tree, ".canary/batches", batch_id[:2], f"{batch_id[2:]}*")
        candidates = glob.glob(pattern)
        if not candidates:
            raise BatchNotFound(f"cannot find stage for batch {batch_id}")
        return "".join(candidates[0].split(os.path.sep)[-2:])

    def setup(self) -> None:
        pass

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
        try:
            breadcrumb = os.path.join(self.stage(self.id), ".running")
            canary.filesystem.touchp(breadcrumb)
            default_int_signal = signal.signal(signal.SIGINT, cancel)
            default_term_signal = signal.signal(signal.SIGTERM, cancel)
            proc: hpc_connect.HPCProcess | None = None
            logger.debug(f"Submitting batch {self.id}")
            if backend.supports_subscheduling and flat:
                scriptdir = os.path.dirname(self.submission_script_filename())
                timeoutx = canary.config.get("config:timeout:multiplier", 1.0)
                variables.pop("CANARY_BATCH_ID", None)
                proc = backend.submitn(
                    [case.id for case in self],
                    [[self.canary_testcase_invocation(case, backend)] for case in self],
                    cpus=[case.cpus for case in self],
                    gpus=[case.gpus for case in self],
                    scriptname=[os.path.join(scriptdir, f"{case.id}-inp.sh") for case in self],
                    output=[os.path.join(scriptdir, f"{case.id}-out.txt") for case in self],
                    error=[os.path.join(scriptdir, f"{case.id}-err.txt") for case in self],
                    submit_flags=list(repeat(get_scheduler_args(), len(self))),
                    variables=list(repeat(variables, len(self))),
                    qtime=[case.runtime * timeoutx for case in self],
                )
            else:
                timeoutx = canary.config.get("config:timeout:multiplier", 1.0)
                qtime = self.qtime() * timeoutx
                nodes = self.nodes_required(backend)
                proc = backend.submit(
                    f"canary.{self.id[:7]}",
                    [self.canary_batch_invocation(backend)],
                    nodes=nodes,
                    scriptname=self.submission_script_filename(),
                    output=self.logfile(self.id),
                    error=self.logfile(self.id),
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
                time.sleep(backend.polling_frequency)
        finally:
            canary.filesystem.force_remove(breadcrumb)
            signal.signal(signal.SIGINT, default_int_signal)
            signal.signal(signal.SIGTERM, default_term_signal)
            self.total_duration = time.monotonic() - start
            self.refresh()
            if all([_.status.satisfies(("ready", "pending")) for _ in self.cases]):
                f = "Batch @*b{%id}: no test cases have started; check %P for any emitted scheduler log files."
                logger.warning(self.format(f))
            for case in self.cases:
                if case.status == "skipped":
                    pass
                elif case.status == "running":
                    logger.debug(f"{case}: cancelling (status: running)")
                    case.status.set("cancelled", "case failed to stop")
                    case.save()
                elif case.start > 0 and case.stop < 0:
                    logger.debug(f"{case}: cancelling (status: {case.status})")
                    case.status.set("cancelled", "case failed to stop")
                    case.save()
                elif case.status == "ready":
                    logger.debug(f"{case}: case failed to start")
                    case.status.set("not_run", f"case failed to start (batch: {self.id})")
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
        self, case: canary.TestCase, backend: hpc_connect.HPCSubmissionManager
    ) -> str:
        """Write the canary invocation used to run this test case"""
        args: list[str] = ["canary"]
        if canary.config.get("config:debug"):
            args.append("-d")
        args.extend(["-C", canary.config.get("session:work_tree")])
        execspec = f"backend:{backend.name},batch:{self.id},case:{case.id}"
        args.extend(["run", f"--hpc-batch-exec={execspec}"])
        return shlex.join(args)

    def canary_batch_invocation(self, backend: hpc_connect.HPCSubmissionManager) -> str:
        """Write the canary invocation used to run this batch."""
        args: list[str] = ["canary"]
        if canary.config.get("config:debug"):
            args.append("-d")
        args.extend(["-C", canary.config.get("session:work_tree")])
        execspec = f"backend:{backend.name},batch:{self.id}"
        args.extend(["run", f"--hpc-batch-exec={execspec}"])
        workers = canary.config.getoption("canary_hpc_batch_workers") or -1
        args.append(f"--workers={workers}")
        return shlex.join(args)


def get_scheduler_args() -> list[str]:
    options: list[str] = []
    if args := canary.config.getoption("canary_hpc_scheduler_args"):
        options.extend(args)
    return options


class BatchNotFound(Exception):
    pass
