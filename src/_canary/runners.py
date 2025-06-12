# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import abc
import io
import json
import os
import shlex
import signal
import subprocess
import time
import warnings
from datetime import datetime
from itertools import repeat
from typing import Any

import hpc_connect
import psutil

from . import config
from .test.atc import AbstractTestCase
from .test.batch import TestBatch
from .test.case import TestCase
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import touchp
from .util.misc import digits
from .util.string import pluralize
from .util.time import hhmmss

HAVE_PSUTIL = True


class AbstractTestRunner:
    """Abstract class for running ``AbstractTestCase``.  This class exists for two reasons:

    1. To provide a __call__ method to ``ProcessPoolExuctor.submit``
    2. To provide a mechanism for a TestBatch to call back to canary to run the the cases in it

    """

    scheduled = False

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        config.null()  # Make sure config is loaded, since this may be called in a new subprocess
        self.run(case, **kwargs)
        return None

    @abc.abstractmethod
    def run(self, obj: AbstractTestCase, **kwargs: Any) -> None: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def run(self, obj: "AbstractTestCase", **kwargs: Any) -> None:
        assert isinstance(obj, TestCase)
        try:
            config.plugin_manager.hook.canary_testcase_setup(case=obj)
            config.plugin_manager.hook.canary_testcase_run(
                case=obj, qsize=kwargs.get("qsize", 1), qrank=kwargs.get("qrank", 1)
            )
        finally:
            config.plugin_manager.hook.canary_testcase_finish(case=obj)


class BatchRunner(AbstractTestRunner):
    """Run a batch of test cases

    The batch runner works by calling canary on itself and requesting the tests in the batch are
    run as exclusive test cases.

    """

    shell = "/bin/sh"
    command_name = "batch-runner"

    def __init__(self) -> None:
        super().__init__()

        # by this point, hpc_connect should have already be set up
        assert config.backend is not None

    @property
    def batch_options(self) -> list[str]:
        batch_options: list[str] = list(config.batch.default_options)
        if varargs := os.getenv("CANARY_BATCH_ARGS"):
            warnings.warn(
                "Use CANARY_RUN_ADDOPTS instead of CANARY_BATCH_ARGS",
                category=DeprecationWarning,
                stacklevel=0,
            )
            batch_options.extend(shlex.split(varargs))
        batchopts = config.getoption("batch", {})
        if args := batchopts.get("options"):
            batch_options.extend(args)
        return batch_options

    def run(self, obj: AbstractTestCase, **kwargs: Any) -> None:
        batch: TestBatch = obj  # type: ignore
        assert isinstance(batch, TestBatch)

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

        logging.trace(f"Running batch {batch.id[:7]}")
        start = time.monotonic()
        variables = dict(batch.variables)
        variables["CANARY_LEVEL"] = "1"
        variables["CANARY_DISABLE_KB"] = "1"
        variables["CANARY_HPCC_BACKEND"] = "null"  # guard against infinite batch recursion
        if config.debug:
            variables["CANARY_DEBUG"] = "on"
            hpc_connect.set_debug(True)

        batchopts = config.getoption("batch", {})
        flat = batchopts["spec"]["layout"] == "flat"
        try:
            breadcrumb = os.path.join(batch.stage(batch.id), ".running")
            touchp(breadcrumb)
            default_int_signal = signal.signal(signal.SIGINT, cancel)
            default_term_signal = signal.signal(signal.SIGTERM, cancel)
            backend = config.backend
            assert backend is not None
            proc: hpc_connect.HPCProcess | None = None
            logging.debug(f"Submitting batch {batch.id}")
            if backend.supports_subscheduling and flat:
                scriptdir = os.path.dirname(batch.submission_script_filename())
                timeoutx = config.getoption("timeout_multiplier", 1.0)
                variables.pop("CANARY_BATCH_ID", None)
                proc = backend.submitn(
                    [case.id for case in batch],
                    [[self.canary_invocation(case)] for case in batch],
                    cpus=[case.cpus for case in batch],
                    gpus=[case.gpus for case in batch],
                    scriptname=[os.path.join(scriptdir, f"{case.id}-inp.sh") for case in batch],
                    output=[os.path.join(scriptdir, f"{case.id}-out.txt") for case in batch],
                    error=[os.path.join(scriptdir, f"{case.id}-err.txt") for case in batch],
                    submit_flags=list(repeat(self.batch_options, len(batch))),
                    variables=list(repeat(variables, len(batch))),
                    qtime=[case.runtime * timeoutx for case in batch],
                )
            else:
                qtime = self.qtime(batch)
                if timeoutx := config.getoption("timeout_multiplier"):
                    qtime *= timeoutx
                proc = backend.submit(
                    f"canary.{batch.id[:7]}",
                    [self.canary_invocation(batch)],
                    nodes=nodes_required(batch),
                    scriptname=batch.submission_script_filename(),
                    output=batch.logfile(batch.id),
                    error=batch.logfile(batch.id),
                    submit_flags=self.batch_options,
                    variables=variables,
                    qtime=qtime,
                )
            assert proc is not None
            if getattr(proc, "jobid", None) not in (None, "none", "<none>"):
                batch.jobid = proc.jobid
            if logging.get_level() <= logging.INFO:
                logging.emit(self.start_msg(batch, **kwargs) + "\n")
            while True:
                if proc.poll() is not None:
                    break
                time.sleep(backend.polling_frequency)
        finally:
            force_remove(breadcrumb)
            signal.signal(signal.SIGINT, default_int_signal)
            signal.signal(signal.SIGTERM, default_term_signal)
            batch.total_duration = time.monotonic() - start
            batch.refresh()
            if all([_.status.satisfies(("ready", "pending")) for _ in batch.cases]):
                fmt = "Batch %id: no test cases have started; check %p for any emitted scheduler log files."
                logging.warning(batch.format(fmt))
            for case in batch.cases:
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
                    case.status.set("not_run", f"case failed to start (batch: {batch.id})")
                    case.save()
            if rc := getattr(proc, "returncode", None):
                logging.error(batch.format(f"Batch %id: batch processing exited with code {rc}"))
            if logging.get_level() <= logging.INFO:
                logging.emit(self.end_msg(batch, **kwargs) + "\n")
        return

    def start_msg(
        self,
        batch: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
        **kwargs: Any,
    ) -> str:
        assert isinstance(batch, TestBatch)
        fmt = io.StringIO()
        fmt.write("@*b{==>} ")
        if config.debug or os.getenv("GITLAB_CI"):
            fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                fmt.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        fmt.write(f"Submitted batch %id: %l {pluralize('test', len(batch))}")
        if batch.jobid:
            fmt.write(" (jobid: %j)")
        return batch.format(fmt.getvalue()).strip()

    def end_msg(
        self,
        batch: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
        **kwargs: Any,
    ) -> str:
        assert isinstance(batch, TestBatch)
        fmt = io.StringIO()
        fmt.write("@*b{==>} ")
        if config.debug or os.getenv("GITLAB_CI"):
            fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                fmt.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        times = batch.times()
        fmt.write(f"Finished batch %id: %bs (time: {hhmmss(times[0], threshold=0)}")
        if times[1]:
            fmt.write(f", running: {hhmmss(times[1], threshold=0)}")
        if times[2]:
            fmt.write(f", queued: {hhmmss(times[2], threshold=0)}")
        fmt.write(")")
        return batch.format(fmt.getvalue()).strip()

    def canary_invocation(self, arg: TestBatch | TestCase) -> str:
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

    def qtime(self, batch: TestBatch) -> float:
        if len(batch.cases) == 1:
            return batch.cases[0].runtime
        total_runtime = batch.runtime
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


def factory() -> "AbstractTestRunner":
    runner: "AbstractTestRunner"
    if config.backend is None:
        runner = TestCaseRunner()
    else:
        runner = BatchRunner()
        if nodes_per_batch := os.getenv("CANARY_NODES_PER_BATCH"):
            sys_node_count = config.resource_pool.pinfo("node_count")
            if int(nodes_per_batch) > config.resource_pool.pinfo("node_count"):
                raise ValueError(
                    f"CANARY_NODES_PER_BATCH={nodes_per_batch} exceeds "
                    f"node count of system ({sys_node_count})"
                )
    return runner


def Popen(*args, **kwargs) -> psutil.Popen:
    if HAVE_PSUTIL:
        return psutil.Popen(*args, **kwargs)
    return subprocess.Popen(*args, **kwargs)
