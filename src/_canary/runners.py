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
from typing import TextIO

import hpc_connect
import psutil

from . import config
from .error import diff_exit_status
from .error import skip_exit_status
from .error import timeout_exit_status
from .status import Status
from .test.atc import AbstractTestCase
from .test.batch import TestBatch
from .test.case import MissingSourceError
from .test.case import TestCase
from .third_party.color import colorize
from .util import logging
from .util.filesystem import working_dir
from .util.misc import digits
from .util.time import hhmmss
from .util.time import timestamp

HAVE_PSUTIL = True


class AbstractTestRunner:
    scheduled = False

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        config.null()
        verbose = logging.get_level() <= logging.INFO
        qsize = kwargs.get("qsize")
        qrank = kwargs.get("qrank")
        id: str
        pretty_name: str
        if isinstance(case, TestCase):
            id = colorize("@b{%s}" % case.id[:7])
            pretty_name = case.pretty_repr()
        if verbose:
            f = io.StringIO()
            f.write(colorize("@*b{==>} "))
            f.write(self.start_msg(case, qsize=qsize, qrank=qrank))
            logging.emit(f.getvalue() + "\n")
        self.run(case)
        if verbose:
            f.seek(0)
            f.write(colorize("@*b{==>} "))
            f.write(self.end_msg(case, qsize=qsize, qrank=qrank))
            logging.emit(f.getvalue() + "\n")
        return None

    @abc.abstractmethod
    def run(self, case: AbstractTestCase) -> None: ...

    @abc.abstractmethod
    def start_msg(
        self,
        case: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str: ...

    @abc.abstractmethod
    def end_msg(
        self,
        case: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def __init__(self) -> None:
        super().__init__()

    def run(self, case: "AbstractTestCase") -> None:
        assert isinstance(case, TestCase)

        def cancel(sig, frame):
            nonlocal proc
            logging.debug(f"Cancelling due to captured signal {sig!r}")
            if proc is None:
                return
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                try:
                    if proc.is_running():
                        proc.send_signal(sig)
                except Exception:
                    pass

        try:
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
                    stdout = open(case.stdout("run"), "w")
                    stderr: TextIO | int
                    if f := case.stderr("run"):
                        stderr = open(f, "w")
                    else:
                        stderr = subprocess.STDOUT
                    cmd = case.command()
                    cmd_line = shlex.join(cmd)
                    stdout.write(f"==> Running {case.display_name}\n")
                    stdout.write(f"==> Working directory: {case.working_directory}\n")
                    stdout.write(f"==> Execution directory: {case.execution_directory}\n")
                    stdout.write(f"==> Command line: {cmd_line}\n")
                    if timeoutx:
                        stdout.write(f"==> Timeout multiplier: {timeoutx}\n")
                    stdout.flush()
                    with case.rc_environ():
                        start_marker: float = time.monotonic()
                        logging.trace(f"Submitting {case} for execution with command {cmd_line}")
                        proc = Popen(
                            cmd,
                            start_new_session=True,
                            stdout=stdout,
                            stderr=stderr,
                            cwd=case.execution_directory,
                        )
                        metrics = self.get_process_metrics(proc)
                        while proc.poll() is None:
                            self.get_process_metrics(proc, metrics=metrics)
                            if timeout > 0 and time.monotonic() - start_marker > timeout:
                                os.kill(proc.pid, signal.SIGINT)
                                raise TimeoutError
                            time.sleep(0.05)
                finally:
                    duration = time.monotonic() - start_marker
                    exit_code = 1 if proc is None else proc.returncode
                    stdout.write(
                        f"==> Finished running {case.display_name} "
                        f"in {duration} s. with exit code {exit_code}\n"
                    )
                    stdout.close()
                    if hasattr(stderr, "close"):
                        stderr.close()  # type: ignore
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
            signal.signal(signal.SIGINT, default_int_handler)
            signal.signal(signal.SIGTERM, default_term_handler)
            if case.status != "skipped":
                case.stop = timestamp()
                if metrics is not None:
                    case.add_measurement(**metrics)
            case.finish()
            logging.trace(f"{case}: finished with status {case.status}")
        return

    def start_msg(
        self,
        case: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(case, TestCase)
        f = io.StringIO()
        if config.debug or os.getenv("GITLAB_CI"):
            f.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                f.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        id = colorize("@b{%s}" % case.id[:7])
        f.write(f"Starting {id}: {case.pretty_repr()}")
        return f.getvalue()

    def end_msg(
        self,
        case: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(case, TestCase)
        f = io.StringIO()
        if config.debug or os.getenv("GITLAB_CI"):
            f.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                f.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        id = colorize("@b{%s}" % case.id[:7])
        f.write(f"Finished {id}: {case.pretty_repr()} {case.status.cname}")
        return f.getvalue()

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

    def run(self, batch: AbstractTestCase) -> None:
        assert isinstance(batch, TestBatch)

        def cancel(sig, frame):
            nonlocal proc
            if proc is None:
                return
            proc.cancel()

        logging.trace(f"Running batch {batch.id[:7]}")
        start = time.monotonic()
        variables = dict(batch.variables)
        variables["CANARY_LEVEL"] = "1"
        variables["CANARY_DISABLE_KB"] = "1"
        variables["CANARY_HPCC_BACKEND"] = "null"  # guard against infinite batch recursion
        if config.debug:
            variables["CANARY_DEBUG"] = "on"
            hpc_connect.set_debug(True)

        if config.debug:
            logging.trace(f"Submitting batch {batch.id[:7]}")

        batchopts = config.getoption("batch", {})
        flat = batchopts["spec"]["layout"] == "flat"
        try:
            default_int_signal = signal.signal(signal.SIGINT, cancel)
            default_term_signal = signal.signal(signal.SIGTERM, cancel)
            backend = config.backend
            assert backend is not None
            proc: hpc_connect.HPCProcess | None = None
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
            while True:
                if proc.poll() is not None:
                    break
                time.sleep(backend.polling_frequency)
        finally:
            signal.signal(signal.SIGINT, default_int_signal)
            signal.signal(signal.SIGTERM, default_term_signal)
            batch.total_duration = time.monotonic() - start
            batch.refresh()
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
                    case.status.set("not_run", "case failed to start")
                    case.save()
        return

    def start_msg(
        self,
        batch: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(batch, TestBatch)
        f = io.StringIO()
        if config.debug or os.getenv("GITLAB_CI"):
            f.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                f.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        n = len(batch.cases)
        id = colorize("@b{%s}" % batch.id[:7])
        f.write(f"Submitting batch {id}: {n} test{'' if n == 1 else 's'}")
        return f.getvalue()

    def end_msg(
        self,
        batch: AbstractTestCase,
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(batch, TestBatch)
        stat: dict[str, int] = {}
        for case in batch.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        fmt = "@%s{%d %s}"
        colors = Status.colors
        st_stat = ", ".join(colorize(fmt % (colors[n], v, n)) for (n, v) in stat.items())

        f = io.StringIO()
        if config.debug or os.getenv("GITLAB_CI"):
            f.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
            if qrank is not None and qsize is not None:
                f.write(f"{qrank + 1:0{digits(qsize)}}/{qsize} ")
        id = colorize("@b{%s}" % batch.id[:7])
        f.write(f"Finished batch {id}: {st_stat}")

        duration: float | None = batch.total_duration if batch.total_duration > 0 else None
        f.write(f"(time: {hhmmss(duration, threshold=0)}")
        if any(_.start > 0 for _ in batch.cases) and any(_.stop > 0 for _ in batch.cases):
            ti = min(_.start for _ in batch.cases if _.start > 0)
            tf = max(_.stop for _ in batch.cases if _.stop > 0)
            f.write(f", running: {hhmmss(tf - ti, threshold=0)}")
            if duration:
                time_in_queue = max(duration - (tf - ti), 0)
                f.write(f", queued: {hhmmss(time_in_queue, threshold=0)}")
        f.write(")")
        return f.getvalue()

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
