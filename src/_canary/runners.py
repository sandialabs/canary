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
import sys
import time
import warnings
from datetime import datetime
from itertools import repeat
from typing import IO
from typing import Any

import hpc_connect
import psutil

from . import config
from .error import diff_exit_status
from .error import skip_exit_status
from .error import timeout_exit_status
from .test.atc import AbstractTestCase
from .test.batch import TestBatch
from .test.case import MissingSourceError
from .test.case import TestCase
from .util import logging
from .util.filesystem import force_remove
from .util.filesystem import touchp
from .util.filesystem import working_dir
from .util.misc import digits
from .util.string import pluralize
from .util.time import hhmmss
from .util.time import timestamp

HAVE_PSUTIL = True


class AbstractTestRunner:
    scheduled = False

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        config.null()
        self.run(case, **kwargs)
        return None

    @abc.abstractmethod
    def run(self, obj: AbstractTestCase, **kwargs: Any) -> None: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def __init__(self) -> None:
        super().__init__()
        self.tee_output = config.getoption("capture") == "tee"

    def run(self, obj: "AbstractTestCase", **kwargs: Any) -> None:
        case = obj
        assert isinstance(case, TestCase)

        def cancel(sig, frame):
            nonlocal proc
            logging.info(f"Cancelling run due to captured signal {sig!r}")
            if proc is not None:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore")
                    try:
                        if proc.is_running():
                            proc.send_signal(sig)
                    except Exception:
                        pass
            if sig == signal.SIGINT:
                raise KeyboardInterrupt
            elif sig == signal.SIGTERM:
                os._exit(1)

        try:
            if logging.get_level() <= logging.INFO:
                logging.emit(self.start_msg(case, **kwargs) + "\n")
            default_int_handler = signal.signal(signal.SIGINT, cancel)
            default_term_handler = signal.signal(signal.SIGTERM, cancel)

            proc: psutil.Popen | None = None
            metrics: dict[str, Any] | None = None
            case.start = timestamp()
            if not config.getoption("dont_restage"):
                case.setup()
            case.status.set("running")
            timeout = case.timeout
            if timeoutx := config.getoption("timeout_multiplier"):
                timeout *= timeoutx
            with working_dir(case.working_directory):
                try:
                    cmd = case.command()
                    cmd_line = shlex.join(cmd)
                    case.stdout.write(f"==> Running {case.display_name}\n")
                    case.stdout.write(f"==> Working directory: {case.working_directory}\n")
                    case.stdout.write(f"==> Execution directory: {case.execution_directory}\n")
                    case.stdout.write(f"==> Command line: {cmd_line}\n")
                    if timeoutx:
                        case.stdout.write(f"==> Timeout multiplier: {timeoutx}\n")
                    case.stdout.flush()
                    with case.rc_environ():
                        start_marker: float = time.monotonic()
                        logging.debug(f"Submitting {case} for execution with command {cmd_line}")
                        cwd = case.execution_directory
                        stdout: IO[Any] | int
                        stderr: IO[Any] | int
                        if self.tee_output:
                            stdout = stderr = subprocess.PIPE
                        else:
                            stdout = case.stdout
                            stderr = subprocess.STDOUT if case.efile is None else case.stderr
                        proc = Popen(cmd, stdout=stdout, stderr=stderr, cwd=cwd)
                        metrics = self.get_process_metrics(proc)
                        while proc.poll() is None:
                            if self.tee_output:
                                self.test_testcase_output(proc, case)
                            self.get_process_metrics(proc, metrics=metrics)
                            if timeout > 0 and time.monotonic() - start_marker > timeout:
                                os.kill(proc.pid, signal.SIGINT)
                                raise TimeoutError
                            time.sleep(0.05)
                finally:
                    duration = time.monotonic() - start_marker
                    exit_code = 1 if proc is None else proc.returncode
                    case.stdout.write(
                        f"==> Finished running {case.display_name} "
                        f"in {duration} s. with exit code {exit_code}\n"
                    )
                    case.stdout.flush()
        except MissingSourceError as e:
            case.returncode = skip_exit_status
            case.status.set("skipped", f"{case}: resource file {e.args[0]} not found")
        except TimeoutError:
            case.returncode = timeout_exit_status
            case.status.set("timeout", f"{case} failed to finish in {timeout:.2f}s.")
        except BaseException:
            case.returncode = 1
            case.status.set("failed", "unknown failure")
            raise
        else:
            case.returncode = proc.returncode
            if case.xstatus == diff_exit_status:
                if case.returncode != diff_exit_status:
                    case.status.set("failed", f"expected {case.name} to diff")
                else:
                    case.status.set("xdiff")
            elif case.xstatus != 0:
                # Expected to fail
                code = case.xstatus
                if code > 0 and case.returncode != code:
                    case.status.set("failed", f"expected {case.name} to exit with code={code}")
                elif case.returncode == 0:
                    case.status.set("failed", f"expected {case.name} to exit with code != 0")
                else:
                    case.status.set("xfail")
            else:
                case.status.set_from_code(case.returncode)
        finally:
            if logging.get_level() <= logging.INFO:
                logging.emit(self.end_msg(case, **kwargs) + "\n")
            signal.signal(signal.SIGINT, default_int_handler)
            signal.signal(signal.SIGTERM, default_term_handler)
            if case.status != "skipped":
                case.stop = timestamp()
                if metrics is not None:
                    case.add_measurement(**metrics)
            case.finish()
            logging.trace(f"{case}: finished with status {case.status}")
        return

    def test_testcase_output(self, proc: psutil.Popen, case: TestCase) -> None:
        text = os.read(proc.stdout.fileno(), 1024).decode("utf-8")
        case.stdout.write(text)
        if self.tee_output:
            sys.stdout.write(text)
        text = os.read(proc.stderr.fileno(), 1024).decode("utf-8")
        if case.stderr:
            case.stderr.write(text)
        else:
            case.stdout.write(text)
        if self.tee_output:
            sys.stderr.write(text)

    def start_msg(
        self,
        case: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
        **kwargs: Any,
    ) -> str:
        assert isinstance(case, TestCase)
        fmt = io.StringIO()
        fmt.write("@*b{==>} ")
        if config.debug or os.getenv("GITLAB_CI"):
            fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                fmt.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        fmt.write("Starting %id: %X")
        return case.format(fmt.getvalue()).strip()

    def end_msg(
        self,
        case: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
        **kwargs: Any,
    ) -> str:
        assert isinstance(case, TestCase)
        fmt = io.StringIO()
        fmt.write("@*b{==>} ")
        if config.debug or os.getenv("GITLAB_CI"):
            fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                fmt.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        fmt.write("Finished %id: %X %sN")
        return case.format(fmt.getvalue()).strip()

    def get_process_metrics(
        self, proc: psutil.Popen, metrics: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        # Collect process information
        metrics = metrics or {}
        try:
            valid_names = set(psutil._as_dict_attrnames)
            skip_names = {
                "cmdline",
                "cpu_affinity",
                "net_connections",
                "cwd",
                "environ",
                "exe",
                "gids",
                "ionice",
                "memory_full_info",
                "memory_maps",
                "threads",
                "name",
                "nice",
                "pid",
                "ppid",
                "status",
                "terminal",
                "uids",
                "username",
            }
            names = valid_names - skip_names
            new_metrics = proc.as_dict(names)
        except psutil.NoSuchProcess:
            logging.debug(f"Process with PID {proc.pid} does not exist.")
        except psutil.AccessDenied:
            logging.debug(f"Access denied to process with PID {proc.pid}.")
        except psutil.ZombieProcess:
            logging.debug(f"Process with PID {proc.pid} is a Zombie process.")
        else:
            for name, metric in new_metrics.items():
                if name == "open_files":
                    files = metrics.setdefault("open_files", [])
                    for f in metric:
                        if f[0] not in files:
                            files.append(f[0])
                elif name == "cpu_times":
                    metrics["cpu_times"] = {"user": metric.user, "system": metric.system}
                elif name in ("num_threads", "cpu_percent", "num_fds", "memory_percent"):
                    n = metrics.setdefault(name, 0)
                    metrics[name] = max(n, metric)
                elif name == "memory_info":
                    for key, val in metric._asdict().items():
                        n = metrics.setdefault(name, {}).setdefault(key, 0)
                        metrics[name][key] = max(n, val)
                elif hasattr(metric, "_asdict"):
                    metrics[name] = dict(metric._asdict())
                else:
                    metrics[name] = metric
        finally:
            return metrics


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
