import abc
import io
import math
import os
import signal
import subprocess
import time
from typing import Any

try:
    import psutil  # type: ignore

    HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False


from . import config
from . import plugin
from .atc import AbstractTestCase
from .error import diff_exit_status
from .status import Status
from .test.batch import TestBatch
from .test.case import TestCase
from .third_party.color import colorize
from .util import logging
from .util.filesystem import working_dir
from .util.time import hhmmss
from .util.time import timestamp


class AbstractTestRunner:
    scheduled = False

    def __init__(self) -> None:
        self.timeoutx = config.test.timeoutx

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        prefix = colorize("@*b{==>} ")
        verbose = kwargs.get("verbose", True)
        progress_bar = not verbose
        stage = kwargs.get("stage", "run")
        if not progress_bar:
            logging.emit("%s%s\n" % (prefix, self.start_msg(case, stage)))
        self.run(case, stage)
        if not progress_bar:
            logging.emit("%s%s\n" % (prefix, self.end_msg(case, stage)))
        return None

    @abc.abstractmethod
    def run(self, case: AbstractTestCase, stage: str = "run") -> None: ...

    @abc.abstractmethod
    def start_msg(self, case: AbstractTestCase, stage: str = "run") -> str: ...

    @abc.abstractmethod
    def end_msg(self, case: AbstractTestCase, stage: str = "run") -> str: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def __init__(self) -> None:
        super().__init__()

    def run(self, case: "AbstractTestCase", stage: str = "run") -> None:
        assert isinstance(case, TestCase)
        if stage in ("baseline", "rebase", "rebaseline"):
            return self.baseline(case)
        try:
            metrics: dict[str, Any] | None = None
            case.start = timestamp()
            case.status.set("running")
            case.prepare_for_launch(stage=stage)
            timeout = case.timeout * self.timeoutx
            with working_dir(case.working_directory):
                with open(case.logfile(stage), "w") as fh:
                    cmd = case.command(stage=stage)
                    case.cmd_line = " ".join(cmd)
                    fh.write(f"==> Running {case.display_name}\n")
                    fh.write(f"==> Command line: {case.cmd_line}\n")
                    if self.timeoutx != 1.0:
                        fh.write(f"==> Timeout multiplier: {self.timeoutx}\n")
                    fh.flush()
                    with case.rc_environ():
                        tic = time.monotonic()
                        proc = Popen(
                            cmd, start_new_session=True, stdout=fh, stderr=subprocess.STDOUT
                        )
                        metrics = self.get_process_metrics(proc)
                        while proc.poll() is None:
                            self.get_process_metrics(proc, metrics=metrics)
                            toc = time.monotonic()
                            if timeout > 0 and toc - tic > timeout:
                                os.kill(proc.pid, signal.SIGINT)
                                raise TimeoutError
                            time.sleep(0.05)
        except KeyboardInterrupt:
            case.returncode = 2
            case.status.set("cancelled", "keyboard interrupt")
            time.sleep(0.01)
            raise
        except TimeoutError:
            case.returncode = -2
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
            if metrics is not None:
                case.add_measurement(**metrics)
            case.finish = timestamp()
            for hook in plugin.hooks():
                hook.test_after_run(case)
            case.finalize(stage)
        return

    def baseline(self, case: "TestCase") -> None:
        logging.emit(self.start_msg(case, "baseline") + "\n")
        if "baseline" not in case.stages:
            logging.warning(f"{case} does not define a baseline stage, skipping")
        else:
            case.do_baseline()
        logging.emit(self.end_msg(case, "baseline ") + "\n")

    def start_msg(self, case: AbstractTestCase, stage: str = "run") -> str:
        assert isinstance(case, TestCase)
        id = colorize("@b{%s}" % case.id[:7])
        st = colorize("@*{%s}" % stage)
        return "Starting stage {0} {1} {2}".format(st, id, case.pretty_repr())

    def end_msg(self, case: AbstractTestCase, stage: str = "run") -> str:
        assert isinstance(case, TestCase)
        id = colorize("@b{%s}" % case.id[:7])
        st = colorize("@*{%s}" % stage)
        return "Finished stage {0} {1} {2} {3}".format(
            st, id, case.pretty_repr(), case.status.cname
        )

    def get_process_metrics(
        self, proc: "psutil.Popen", metrics: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        # Collect process information
        if not HAVE_PSUTIL:
            return None
        metrics = metrics or {}
        try:
            valid_names = set(psutil._as_dict_attrnames)
            skip_names = {
                "cmdline",
                "net_connections",
                "cwd",
                "environ",
                "exe",
                "gids",
                "ionice",
                "memory_full_info",
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

    The batch runner works by calling nvtest on itself and requesting the tests in the batch are
    run as exclusive test cases.

    """

    shell = "/bin/sh"
    command_name = "batch-runner"

    def __init__(self) -> None:
        import hpc_connect

        super().__init__()

        # by this point, hpc_connect should have already be set up
        if hpc_connect.backend._scheduler is None:  # type: ignore
            hpc_connect.set(scheduler=config.batch.scheduler)  # type: ignore
        self.scheduler = hpc_connect.scheduler  # type: ignore
        if config.batch.scheduler_args:
            self.scheduler.add_default_args(*config.batch.scheduler_args)

    def run(self, batch: AbstractTestCase, stage: str = "run") -> None:
        import hpc_connect

        assert isinstance(batch, TestBatch)
        try:
            logging.debug(f"Running batch {batch.batch_no}")
            start = time.monotonic()
            variables = dict(batch.variables)
            variables["NVTEST_LEVEL"] = "1"
            variables["NVTEST_DISABLE_KB"] = "1"
            variables["NVTEST_BATCH_SCHEDULER"] = "null"  # guard against infinite batch recursion
            jobs: list[hpc_connect.Job] = []
            if config.batch.scheme == "isolate" and self.scheduler.supports_subscheduling:
                scriptdir = os.path.dirname(batch.submission_script_filename())
                for case in batch:
                    nvtest_invocation = self.nvtest_invocation(case, stage=stage)
                    job = hpc_connect.Job(
                        name=case.name,
                        commands=[nvtest_invocation],
                        tasks=case.cpus,
                        script=os.path.join(scriptdir, f"{case.name}-inp.sh"),
                        output=os.path.join(scriptdir, f"{case.name}-out.txt"),
                        error=os.path.join(scriptdir, f"{case.name}-err.txt"),
                        qtime=case.runtime * self.timeoutx,
                        variables=variables,
                    )
                    jobs.append(job)
            else:
                nvtest_invocation = self.nvtest_invocation(batch, stage=stage)
                job = hpc_connect.Job(
                    name=batch.name,
                    commands=[nvtest_invocation],
                    tasks=batch.max_cpus_required,
                    script=batch.submission_script_filename(),
                    output=batch.logfile(),
                    error=batch.logfile(),
                    qtime=self.qtime(batch) * self.timeoutx,
                    variables=variables,
                )
                jobs.append(job)
            if config.debug:
                logging.debug(f"Submitting batch {batch.batch_no} of {batch.nbatches}")
            self.scheduler.submit_and_wait(*jobs, independent=config.batch.scheme == "isolate")
        except hpc_connect.HPCSubmissionFailedError:
            logging.error(f"Failed to submit {batch.name}!")
            for case in batch.cases:
                if case.status.value in ("ready", "pending"):
                    case.status.set("not_run", "batch submission failed")
                    case.save()
        finally:
            batch.total_duration = time.monotonic() - start
            batch.refresh()
            for case in batch.cases:
                if case.status == "ready":
                    case.status.set("not_run", "case failed to start")
                    case.save()
                elif case.status == "running":
                    case.status.set("cancelled", "batch cancelled")
                    case.save()
        return

    def start_msg(self, batch: AbstractTestCase, stage: str = "run") -> str:
        assert isinstance(batch, TestBatch)
        n = len(batch.cases)
        return f"Submitting batch {batch.batch_no} of {batch.nbatches} ({n} tests)"

    def end_msg(self, batch: AbstractTestCase, stage: str = "run") -> str:
        assert isinstance(batch, TestBatch)
        stat: dict[str, int] = {}
        for case in batch.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        fmt = "@%s{%d %s}"
        colors = Status.colors
        st_stat = ", ".join(colorize(fmt % (colors[n], v, n)) for (n, v) in stat.items())
        duration: float | None = batch.total_duration if batch.total_duration > 0 else None
        s = io.StringIO()
        s.write(f"Finished batch {batch.batch_no} of {batch.nbatches}, {st_stat} ")
        s.write(f"(time: {hhmmss(duration, threshold=0)}")
        if any(_.start > 0 for _ in batch.cases) and any(_.finish > 0 for _ in batch.cases):
            ti = min(_.start for _ in batch.cases if _.start > 0)
            tf = max(_.finish for _ in batch.cases if _.finish > 0)
            s.write(f", running: {hhmmss(tf - ti, threshold=0)}")
            if duration:
                time_in_queue = max(duration - (tf - ti), 0)
                s.write(f", queued: {hhmmss(time_in_queue, threshold=0)}")
        s.write(")")
        return s.getvalue()

    def nvtest_invocation(self, arg: TestBatch | TestCase, stage: str = "run") -> str:
        """Write the nvtest invocation used to run this batch."""

        fp = io.StringIO()
        fp.write("nvtest ")
        if config.debug:
            fp.write("-d ")
        if getattr(config.options, "plugin_dirs", None):
            for p in config.options.plugin_dirs:
                fp.write(f"-p {p} ")

        # The batch will be run in a compute node, so hpc_connect won't set the machine limits
        tasks = arg.max_cpus_required if isinstance(arg, TestBatch) else arg.cpus
        node_count = math.ceil(tasks / self.scheduler.config.cpus_per_node)
        fp.write(f"-c machine:node_count:{node_count} ")
        fp.write(f"-c machine:cpus_per_node:{config.machine.cpus_per_node} ")
        fp.write(f"-c machine:gpus_per_node:{config.machine.gpus_per_node} ")
        fp.write(f"-C {config.session.work_tree} run -rv --stage={stage} ")
        if getattr(config.options, "fail_fast", False):
            fp.write("--fail-fast ")
        if getattr(config.options, "dont_measure", False):
            fp.write("--dont-measure ")
        if p := getattr(config.options, "P", None):
            if p != "pedantic":
                fp.write(f"-P{p} ")
        if isinstance(arg, TestBatch) and config.batch.workers is not None:
            fp.write(f"-l session:workers={config.batch.workers} ")
        fp.write(f"-l session:cpu_count={node_count * config.machine.cpus_per_node} ")
        fp.write(f"-l session:gpu_count={node_count * config.machine.gpus_per_node} ")
        fp.write(f"-l test:timeoutx={self.timeoutx} ")
        fp.write("-l batch:scheduler=null ")  # guard against infinite batch recursion
        if isinstance(arg, TestBatch):
            fp.write(f"^{arg.lot_no}:{arg.batch_no}")
        else:
            fp.write(f"/{arg.id}")
        return fp.getvalue()

    def qtime(self, batch: TestBatch) -> float:
        if len(batch.cases) == 1:
            return batch.cases[0].timeout
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
            total_runtime *= 1.1
        return total_runtime


def factory() -> "AbstractTestRunner":
    runner: "AbstractTestRunner"
    if config.batch.scheduler is None:
        runner = TestCaseRunner()
    else:
        runner = BatchRunner()
    return runner


def Popen(*args, **kwargs) -> "subprocess.Popen | psutil.Popen":
    if HAVE_PSUTIL:
        return psutil.Popen(*args, **kwargs)
    return subprocess.Popen(*args, **kwargs)
