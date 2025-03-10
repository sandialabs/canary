import abc
import io
import json
import os
import shlex
import signal
import subprocess
import time
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
from .util.time import hhmmss
from .util.time import timestamp

HAVE_PSUTIL = True


class AbstractTestRunner:
    scheduled = False

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        verbose = logging.get_level() <= logging.INFO
        prefix = colorize("@*b{==>} ")
        stage = kwargs.get("stage", "run")
        qsize = kwargs.get("qsize")
        qrank = kwargs.get("qrank")
        if verbose:
            logging.emit("%s%s\n" % (prefix, self.start_msg(case, stage, qsize=qsize, qrank=qrank)))
        self.run(case, stage)
        if verbose:
            logging.emit("%s%s\n" % (prefix, self.end_msg(case, stage, qsize=qsize, qrank=qrank)))
        return None

    @abc.abstractmethod
    def run(self, case: AbstractTestCase, stage: str = "run") -> None: ...

    @abc.abstractmethod
    def start_msg(
        self,
        case: AbstractTestCase,
        stage: str = "run",
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str: ...

    @abc.abstractmethod
    def end_msg(
        self,
        case: AbstractTestCase,
        stage: str = "run",
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def __init__(self) -> None:
        super().__init__()

    def run(self, case: "AbstractTestCase", stage: str = "run") -> None:
        assert isinstance(case, TestCase)
        if stage in ("baseline", "rebase", "rebaseline"):
            return self.baseline(case)
        try:
            proc: psutil.Popen | None = None
            metrics: dict[str, Any] | None = None
            case.start = timestamp()
            case.setup(stage=stage)
            case.status.set("running")
            timeout = case.timeout
            if timeoutx := config.getoption("timeout_multiplier"):
                timeout *= timeoutx
            with working_dir(case.working_directory):
                try:
                    stdout = open(case.stdout(stage), "w")
                    stderr: TextIO | int
                    if f := case.stderr(stage):
                        stderr = open(f, "w")
                    else:
                        stderr = subprocess.STDOUT
                    cmd = case.command(stage=stage)
                    case.cmd_line = " ".join(cmd)
                    stdout.write(f"==> Running {case.display_name} in {case.working_directory}\n")
                    stdout.write(f"==> Command line: {case.cmd_line}\n")
                    if timeoutx:
                        stdout.write(f"==> Timeout multiplier: {timeoutx}\n")
                    stdout.flush()
                    with case.rc_environ():
                        tic = time.monotonic()
                        proc = Popen(cmd, start_new_session=True, stdout=stdout, stderr=stderr)
                        metrics = self.get_process_metrics(proc)
                        while proc.poll() is None:
                            self.get_process_metrics(proc, metrics=metrics)
                            toc = time.monotonic()
                            if timeout > 0 and toc - tic > timeout:
                                os.kill(proc.pid, signal.SIGINT)
                                raise TimeoutError
                            time.sleep(0.05)
                finally:
                    stdout.close()
                    if hasattr(stderr, "close"):
                        stderr.close()  # type: ignore
        except MissingSourceError as e:
            case.returncode = skip_exit_status
            case.status.set("skipped", f"{case}: resource file {e.args[0]} not found")
        except KeyboardInterrupt:
            case.returncode = signal.SIGINT.value
            case.status.set("cancelled", "keyboard interrupt")
            time.sleep(0.01)
            raise
        except TimeoutError:
            case.returncode = timeout_exit_status
            case.status.set("timeout", f"{case} failed to finish in {timeout:.2f}s.")
        except BaseException:
            case.returncode = 1
            case.status.set("failed", "unknown failure")
            time.sleep(0.01)
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
            if case.status != "skipped":
                case.stop = timestamp()
                if metrics is not None:
                    case.add_measurement(**metrics)
            case.finish(stage=stage)
        return

    def baseline(self, case: "TestCase") -> None:
        logging.emit(self.start_msg(case, "baseline") + "\n")
        if "baseline" not in case.stages:
            logging.warning(f"{case} does not define a baseline stage, skipping")
        else:
            case.do_baseline()
        logging.emit(self.end_msg(case, "baseline ") + "\n")

    def start_msg(
        self,
        case: AbstractTestCase,
        stage: str = "run",
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(case, TestCase)
        f = io.StringIO()
        id = colorize("@b{%s}" % case.id[:7])
        f.write(f"Starting {id}: {case.pretty_repr()}")
        return f.getvalue()

    def end_msg(
        self,
        case: AbstractTestCase,
        stage: str = "run",
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(case, TestCase)
        f = io.StringIO()
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
        assert config.scheduler is not None
        # a reference to config.scheduler needs to be made since session.run spawns new processes.
        # Otherwise, if we just referenced config.scheduler throughout, the modifications to the
        # scheduler (eg, add_default_args) are lost in spawned uses of config.scheduler.
        self.scheduler: hpc_connect.HPCScheduler = config.scheduler
        batch_options: list[str] = list(config.batch.default_options)
        if varargs := os.getenv("CANARY_BATCH_ARGS"):
            logging.debug(f"Using batch arguments from environment: {varargs}")
            batch_options.extend(shlex.split(varargs))
        batchopts = config.getoption("batch", {})
        if args := batchopts.get("options"):
            batch_options.extend(args)
        self.scheduler.add_default_args(*batch_options)

    def run(self, batch: AbstractTestCase, stage: str = "run") -> None:
        assert isinstance(batch, TestBatch)
        try:
            logging.debug(f"Running batch {batch.id[:7]}")
            start = time.monotonic()
            variables = dict(batch.variables)
            variables["CANARY_LEVEL"] = "1"
            variables["CANARY_DISABLE_KB"] = "1"
            variables["CANARY_BATCH_SCHEDULER"] = "null"  # guard against infinite batch recursion
            if config.debug:
                variables["CANARY_DEBUG"] = "on"

            jobs: list[hpc_connect.Job] = []
            batchopts = config.getoption("batch", {})
            scheme = batchopts.get("scheme")
            if scheme == "isolate" and self.scheduler.supports_subscheduling:
                scriptdir = os.path.dirname(batch.submission_script_filename())
                timeoutx = config.getoption("timeout_multiplier", 1.0)
                variables.pop("CANARY_BATCH_ID", None)
                for case in batch:
                    canary_invocation = self.canary_invocation(case, stage=stage)
                    job = hpc_connect.Job(
                        name=case.name,
                        commands=[canary_invocation],
                        tasks=case.cpus,
                        script=os.path.join(scriptdir, f"{case.name}-inp.sh"),
                        output=os.path.join(scriptdir, f"{case.name}-out.txt"),
                        error=os.path.join(scriptdir, f"{case.name}-err.txt"),
                        qtime=case.runtime * timeoutx,
                        variables=variables,
                    )
                    jobs.append(job)
            else:
                canary_invocation = self.canary_invocation(batch, stage=stage)
                qtime = self.qtime(batch)
                if timeoutx := config.getoption("timeout_multiplier"):
                    qtime *= timeoutx
                job = hpc_connect.Job(
                    name=f"canary.{batch.id[:7]}",
                    commands=[canary_invocation],
                    tasks=max(_.cpus for _ in batch),
                    script=batch.submission_script_filename(),
                    output=batch.logfile(batch.id),
                    error=batch.logfile(batch.id),
                    qtime=qtime,
                    variables=variables,
                )
                jobs.append(job)
            if config.debug:
                logging.debug(f"Submitting batch {batch.id[:7]}")
            self.scheduler.submit_and_wait(*jobs, sequential=scheme != "isolate")
        except hpc_connect.HPCSubmissionFailedError:
            logging.error(f"Failed to submit {batch.id[:7]}!")
            for case in batch.cases:
                if case.status.value in ("ready", "pending"):
                    case.status.set("not_run", "batch submission failed")
                    case.save()
        finally:
            batch.total_duration = time.monotonic() - start
            batch.refresh()
            for case in batch.cases:
                if case.status == "skipped":
                    pass
                elif case.status == "running":
                    case.status.set("cancelled", "case failed to stop")
                    case.save()
                elif case.start > 0 and case.stop < 0:
                    case.status.set("cancelled", "case failed to stop")
                    case.save()
                elif case.status == "ready":
                    case.status.set("not_run", "case failed to start")
                    case.save()
        return

    def start_msg(
        self,
        batch: AbstractTestCase,
        stage: str = "run",
        qsize: int | None = None,
        qrank: int | None = None,
    ) -> str:
        assert isinstance(batch, TestBatch)
        n = len(batch.cases)
        f = io.StringIO()
        id = colorize("@b{%s}" % batch.id[:7])
        f.write(f"Submitting batch {id}: {n} tests")
        return f.getvalue()

    def end_msg(
        self,
        batch: AbstractTestCase,
        stage: str = "run",
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
        duration: float | None = batch.total_duration if batch.total_duration > 0 else None
        f = io.StringIO()
        id = colorize("@b{%s}" % batch.id[:7])
        f.write(f"Finished batch {id}: {st_stat} ")
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

    def canary_invocation(self, arg: TestBatch | TestCase, stage: str = "run") -> str:
        """Write the canary invocation used to run this batch."""

        fp = io.StringIO()
        fp.write("canary ")

        # The batch will be run in a compute node, so hpc_connect won't set the machine limits
        nodes: int
        if isinstance(arg, TestCase):
            nodes = config.resource_pool.nodes_required(arg.required_resources())
        else:
            nodes = max(config.resource_pool.nodes_required(c.required_resources()) for c in arg)
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
        fp.write(f"-C {config.session.work_tree} run -rv --stage={stage} ")
        if config.getoption("fail_fast"):
            fp.write("--fail-fast ")
        if config.getoption("dont_measure"):
            fp.write("--dont-measure ")
        if p := config.getoption("P"):
            if p != "pedantic":
                fp.write(f"-P{p} ")
        if isinstance(arg, TestBatch):
            batchopts = config.getoption("batch", {})
            if workers := batchopts.get("workers"):
                fp.write(f"--workers={workers} ")
        if timeoutx := config.getoption("timeout_multiplier"):
            fp.write(f"--timeout-multiplier={timeoutx} ")
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


def factory() -> "AbstractTestRunner":
    runner: "AbstractTestRunner"
    if config.scheduler is None:
        runner = TestCaseRunner()
    else:
        runner = BatchRunner()
    return runner


def Popen(*args, **kwargs) -> psutil.Popen:
    if HAVE_PSUTIL:
        return psutil.Popen(*args, **kwargs)
    return subprocess.Popen(*args, **kwargs)
