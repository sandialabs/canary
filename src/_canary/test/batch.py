# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import io
import json
import math
import os
import shlex
import signal
import time
import warnings
from datetime import datetime
from itertools import repeat
from typing import Any
from typing import Sequence

import hpc_connect

from .. import config
from ..status import Status
from ..third_party.color import colorize
from ..util import logging
from ..util.filesystem import force_remove
from ..util.filesystem import mkdirp
from ..util.filesystem import touchp
from ..util.hash import hashit
from ..util.misc import digits
from ..util.string import pluralize
from ..util.time import hhmmss
from .atc import AbstractTestCase
from .case import TestCase


class TestBatch(AbstractTestCase):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch

    """

    def __init__(
        self,
        cases: Sequence[TestCase],
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
        self._runtime: float | None = runtime
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
        from ..util import partitioning

        if self._runtime is None:
            if len(self.cases) == 1:
                self._runtime = self.cases[0].runtime
            else:
                _, height = partitioning.packed_perimeter(self.cases)
                t = sum(c.runtime for c in self)
                self._runtime = float(min(height, t))
        assert self._runtime is not None
        return self._runtime

    def qtime(self) -> float:
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

    def validate(self, cases: Sequence[TestCase]):
        errors = 0
        for case in cases:
            if case.masked():
                logging.fatal(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.masked():
                    errors += 1
                    logging.fatal(f"{dep}: dependent of {case} is masked")
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

    def save(self):
        f = os.path.join(self.stage(self.id), "index")
        mkdirp(os.path.dirname(f))
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
        return ", ".join(colorize("@%s{%d %s}" % (colors[v], n, v)) for (v, n) in stat.items())

    def format(self, format_spec: str) -> str:
        state = self.status
        times = self.times()
        replacements: dict[str, str] = {
            "%id": "@*b{%s}" % self.id[:7],
            "%p": self.path,
            "%n": repr(self),
            "%sN": self.status.cname,
            "%sn": state.value,
            "%sd": state.details or "unknown",
            "%l": str(len(self)),
            "%bs": self._combined_status(),
            "%d": hhmmss(times[0], threshold=0),  # duration
            "%tr": hhmmss(times[1], threshold=0),  # running time
            "%tq": hhmmss(times[2], threshold=0),  # time in queue
            "%j": self.jobid or "none",
        }
        if config.getoption("format", "short") == "long":
            replacements["%X"] = replacements["%p"]
        else:
            replacements["%X"] = replacements["%n"]
        formatted_text = format_spec
        for placeholder, value in replacements.items():
            formatted_text = formatted_text.replace(placeholder, value)
        return colorize(formatted_text.strip())

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
    def loadindex(batch_id: str) -> list[str] | None:
        try:
            full_batch_id = TestBatch.find(batch_id)
        except BatchNotFound:
            return None
        stage = TestBatch.stage(full_batch_id)
        f = os.path.join(stage, "index")
        if not os.path.exists(f):
            return None
        with open(f, "r") as fh:
            return json.load(fh)

    @staticmethod
    def stage(batch_id: str) -> str:
        work_tree = config.session.work_tree
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
        work_tree = config.session.work_tree
        assert work_tree is not None
        pattern = os.path.join(work_tree, ".canary/batches", batch_id[:2], f"{batch_id[2:]}*")
        candidates = glob.glob(pattern)
        if not candidates:
            raise BatchNotFound(f"cannot find stage for batch {batch_id}")
        return "".join(candidates[0].split(os.path.sep)[-2:])

    def setup(self) -> None:
        pass

    def run(self, qsize: int = 1, qrank: int = 1) -> None:
        def cancel(sig, frame):
            nonlocal proc
            logging.info(f"Cancelling run due to captured signal {sig!r}")
            if proc is not None:
                logging.info("Cancelling hpc-connect process")
                proc.cancel()
            if sig == signal.SIGINT:
                raise KeyboardInterrupt
            elif sig == signal.SIGTERM:
                os._exit(1)

        logging.trace(f"Running batch {self.id[:7]}")
        start = time.monotonic()
        variables = dict(self.variables)
        variables["CANARY_LEVEL"] = "1"
        variables["CANARY_DISABLE_KB"] = "1"
        variables["CANARY_HPCC_BACKEND"] = "null"  # guard against infinite batch recursion
        if config.debug:
            variables["CANARY_DEBUG"] = "on"
            hpc_connect.set_debug(True)

        batchopts = config.getoption("batch", {})
        flat = batchopts["spec"]["layout"] == "flat"
        try:
            breadcrumb = os.path.join(self.stage(self.id), ".running")
            touchp(breadcrumb)
            default_int_signal = signal.signal(signal.SIGINT, cancel)
            default_term_signal = signal.signal(signal.SIGTERM, cancel)
            backend = config.backend
            assert backend is not None
            proc: hpc_connect.HPCProcess | None = None
            logging.debug(f"Submitting batch {self.id}")
            if backend.supports_subscheduling and flat:
                scriptdir = os.path.dirname(self.submission_script_filename())
                timeoutx = config.getoption("timeout_multiplier", 1.0)
                variables.pop("CANARY_BATCH_ID", None)
                proc = backend.submitn(
                    [case.id for case in self],
                    [[canary_invocation(case)] for case in self],
                    cpus=[case.cpus for case in self],
                    gpus=[case.gpus for case in self],
                    scriptname=[os.path.join(scriptdir, f"{case.id}-inp.sh") for case in self],
                    output=[os.path.join(scriptdir, f"{case.id}-out.txt") for case in self],
                    error=[os.path.join(scriptdir, f"{case.id}-err.txt") for case in self],
                    submit_flags=list(repeat(batch_options(), len(self))),
                    variables=list(repeat(variables, len(self))),
                    qtime=[case.runtime * timeoutx for case in self],
                )
            else:
                qtime = self.qtime()
                if timeoutx := config.getoption("timeout_multiplier"):
                    qtime *= timeoutx
                proc = backend.submit(
                    f"canary.{self.id[:7]}",
                    [canary_invocation(self)],
                    nodes=nodes_required(self),
                    scriptname=self.submission_script_filename(),
                    output=self.logfile(self.id),
                    error=self.logfile(self.id),
                    submit_flags=batch_options(),
                    variables=variables,
                    qtime=qtime,
                )
            assert proc is not None
            if getattr(proc, "jobid", None) not in (None, "none", "<none>"):
                self.jobid = proc.jobid
            if logging.get_level() <= logging.INFO:
                fmt = io.StringIO()
                fmt.write("@*b{==>} ")
                if config.debug or os.getenv("GITLAB_CI"):
                    fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
                    if qrank is not None and qsize is not None:
                        fmt.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
                fmt.write(f"Submitted batch %id: %l {pluralize('test', len(self))}")
                if self.jobid:
                    fmt.write(" (jobid: %j)")
                logging.emit(self.format(fmt.getvalue()).strip() + "\n")
            while True:
                if proc.poll() is not None:
                    break
                time.sleep(backend.polling_frequency)
        finally:
            force_remove(breadcrumb)
            signal.signal(signal.SIGINT, default_int_signal)
            signal.signal(signal.SIGTERM, default_term_signal)
            self.total_duration = time.monotonic() - start
            self.refresh()
            if all([_.status.satisfies(("ready", "pending")) for _ in self.cases]):
                f = "Batch %id: no test cases have started; check %p for any emitted scheduler log files."
                logging.warning(self.format(f))
            for case in self.cases:
                if case.status == "skipped":
                    pass
                elif case.status == "running":
                    logging.debug(f"{case}: cancelling (status: running)")
                    case.status.set("cancelled", "case failed to stop")
                    case.save()
                elif case.start > 0 and case.stop < 0:
                    logging.debug(f"{case}: cancelling (status: {case.status})")
                    case.status.set("cancelled", "case failed to stop")
                    case.save()
                elif case.status == "ready":
                    logging.debug(f"{case}: case failed to start")
                    case.status.set("not_run", f"case failed to start (batch: {self.id})")
                    case.save()
            if rc := getattr(proc, "returncode", None):
                logging.debug(self.format(f"Batch %id: batch processing exited with code {rc}"))
            if logging.get_level() <= logging.INFO:
                fmt = io.StringIO()
                fmt.write("@*b{==>} ")
                if config.debug or os.getenv("GITLAB_CI"):
                    fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
                    if qrank is not None and qsize is not None:
                        fmt.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
                times = self.times()
                fmt.write(f"Finished batch %id: %bs (time: {hhmmss(times[0], threshold=0)}")
                if times[1]:
                    fmt.write(f", running: {hhmmss(times[1], threshold=0)}")
                if times[2]:
                    fmt.write(f", queued: {hhmmss(times[2], threshold=0)}")
                fmt.write(")")
                logging.emit(self.format(fmt.getvalue()).strip() + "\n")

        return

    def finish(self) -> None:
        pass


def canary_invocation(arg: "TestBatch | TestCase") -> str:
    """Write the canary invocation used to run this batch."""

    fp = io.StringIO()
    fp.write("canary ")

    # The batch will be run in a compute node, so hpc_connect won't set the machine limits
    nodes = nodes_required(arg)
    cpus_per_node = config.resource_pool.pinfo("cpus_per_node")
    gpus_per_node = config.resource_pool.pinfo("gpus_per_node")
    if isinstance(arg, TestBatch):
        cfg: dict[str, Any] = {}
        pool = cfg.setdefault("resource_pool", {})
        pool["nodes"] = nodes
        pool["cpus_per_node"] = cpus_per_node
        pool["gpus_per_node"] = gpus_per_node
        batch_stage = arg.stage(arg.id)
        config_file = os.path.join(batch_stage, "config")
        with open(config_file, "w") as fh:
            json.dump(cfg, fh, indent=2)
        fp.write(f"-f {config_file} ")
    if config.debug:
        fp.write("-d ")
    fp.write(f"-C {config.session.work_tree} run ")
    if isinstance(arg, TestBatch):
        batchopts = config.getoption("batch", {})
        if workers := batchopts.get("workers"):
            fp.write(f"--workers={workers} ")
    fp.write("-b scheduler=null ")  # guard against infinite batch recursion
    sigil = "^" if isinstance(arg, TestBatch) else "/"
    fp.write(f"{sigil}{arg.id}")
    return fp.getvalue()


def nodes_required(arg: TestCase | TestBatch) -> int:
    nodes: int
    if isinstance(arg, TestCase):
        nodes = config.resource_pool.nodes_required(arg.required_resources())
    else:
        assert isinstance(arg, TestBatch)
        nodes = max(config.resource_pool.nodes_required(c.required_resources()) for c in arg)
        if nodes_per_batch := os.getenv("CANARY_NODES_PER_BATCH"):
            nodes = max(nodes, int(nodes_per_batch))
    return nodes


def batch_options() -> list[str]:
    options: list[str] = list(config.batch.default_options)
    if varargs := os.getenv("CANARY_BATCH_ARGS"):
        warnings.warn(
            "Use CANARY_RUN_ADDOPTS instead of CANARY_BATCH_ARGS",
            category=DeprecationWarning,
            stacklevel=0,
        )
        options.extend(shlex.split(varargs))
    batchopts = config.getoption("batch", {})
    if args := batchopts.get("options"):
        options.extend(args)
    return options


class BatchNotFound(Exception):
    pass
