import abc
import io
import math
import os
import signal
import subprocess
import time
from typing import Any
from typing import Optional

from . import config
from .atc import AbstractTestCase
from .error import diff_exit_status
from .resource import ResourceHandler
from .status import Status
from .test.batch import TestBatch
from .test.case import TestCase
from .third_party.color import colorize
from .util import logging
from .util.filesystem import mkdirp
from .util.filesystem import set_executable
from .util.filesystem import working_dir
from .util.time import hhmmss
from .util.time import timestamp


class AbstractTestRunner:
    scheduled = False

    def __init__(self, rh: ResourceHandler) -> None:
        self.rh = rh
        self.timeoutx = self.rh["test:timeoutx"]

    def __call__(self, case: AbstractTestCase, *args: str, **kwargs: Any) -> None:
        prefix = colorize("@*b{==>} ")
        if not config.getoption("progress_bar"):
            logging.emit("%s%s\n" % (prefix, self.start_msg(case)))
        self.run(case)
        if not config.getoption("progress_bar"):
            logging.emit("%s%s\n" % (prefix, self.end_msg(case)))
        return None

    @abc.abstractmethod
    def run(self, case: AbstractTestCase, stage: str = "test") -> None: ...

    @abc.abstractmethod
    def start_msg(self, case: AbstractTestCase) -> str: ...

    @abc.abstractmethod
    def end_msg(self, case: AbstractTestCase) -> str: ...


class TestCaseRunner(AbstractTestRunner):
    """The default runner for running a single :class:`~TestCase`"""

    def __init__(self, rh: ResourceHandler) -> None:
        super().__init__(rh)

    def run(self, case: "AbstractTestCase", stage: str = "test") -> None:
        assert isinstance(case, TestCase)
        assert stage in ("test", "analyze")
        try:
            case.start = timestamp()
            case.status.set("running")
            case.prepare_for_launch(stage=stage)
            timeout = case.timeout * self.timeoutx
            with working_dir(case.working_directory):
                with logging.capture(case.logfile(stage), mode="w"), logging.timestamps():
                    cmd = case.command(stage=stage)
                    case.cmd_line = " ".join(cmd)
                    logging.info(f"Running {case.display_name}")
                    logging.info(f"Command line: {case.cmd_line}")
                    if self.timeoutx != 1.0:
                        logging.info(f"Timeout multiplier: {self.timeoutx}")
                    with case.rc_environ():
                        tic = time.monotonic()
                        proc = subprocess.Popen(cmd, start_new_session=True)
                        while True:
                            if proc.poll() is not None:
                                break
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
            case.finish = timestamp()
            case.wrap_up()
        return

    def analyze(self, case: "TestCase") -> None:
        logging.emit(self.start_msg(case) + "\n")
        self.run(case, stage="analyze")
        logging.emit(self.end_msg(case) + "\n")

    def start_msg(self, case: AbstractTestCase) -> str:
        assert isinstance(case, TestCase)
        id = colorize("@b{%s}" % case.id[:7])
        return "Starting {0} {1}".format(id, case.pretty_repr())

    def end_msg(self, case: AbstractTestCase) -> str:
        assert isinstance(case, TestCase)
        id = colorize("@b{%s}" % case.id[:7])
        return "Finished {0} {1} {2}".format(id, case.pretty_repr(), case.status.cname)


class BatchRunner(AbstractTestRunner):
    """Run a batch of test cases

    The batch runner works by calling nvtest on itself and requesting the tests in the batch are
    run as exclusive test cases.

    """

    shell = "/bin/sh"
    command_name = "batch-runner"

    def __init__(self, rh: ResourceHandler) -> None:
        import hpc_connect

        super().__init__(rh)

        # by this point, hpc_connect should have already be set up
        if hpc_connect.backend._scheduler is None:  # type: ignore
            hpc_connect.set(scheduler=self.rh["batch:scheduler"])  # type: ignore
        self.scheduler = hpc_connect.scheduler  # type: ignore
        if self.rh["batch:scheduler_args"]:
            args = self.rh["batch:scheduler_args"]
            self.scheduler.add_default_args(*args)

    def run(self, batch: AbstractTestCase, stage: str = "test") -> None:
        import hpc_connect

        assert isinstance(batch, TestBatch)
        try:
            logging.debug(f"Running batch {batch.batch_no}")
            start = time.monotonic()
            node_count = math.ceil(batch.max_cpus_required / self.scheduler.config.cpus_per_node)
            nvtest_invocation = self.nvtest_invocation(batch, node_count=node_count)
            scriptname = batch.submission_script_filename()
            mkdirp(os.path.dirname(scriptname))
            with open(scriptname, "w") as fh:
                self.scheduler.write_submission_script(
                    [nvtest_invocation],
                    fh,
                    tasks=batch.max_cpus_required,
                    nodes=node_count,
                    job_name=batch.name,
                    output=batch.logfile(),
                    error=batch.logfile(),
                    qtime=self.qtime(batch) * self.timeoutx,
                    variables=batch.variables,
                )
            set_executable(scriptname)
            if config.get("config:debug"):
                logging.debug(f"Submitting batch {batch.batch_no} of {batch.nbatches}")
            self.scheduler.submit_and_wait(scriptname, job_name=batch.name)
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

    def start_msg(self, batch: AbstractTestCase) -> str:
        assert isinstance(batch, TestBatch)
        n = len(batch.cases)
        return f"Submitting batch {batch.batch_no} of {batch.nbatches} ({n} tests)"

    def end_msg(self, batch: AbstractTestCase) -> str:
        assert isinstance(batch, TestBatch)
        stat: dict[str, int] = {}
        for case in batch.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        fmt = "@%s{%d %s}"
        colors = Status.colors
        st_stat = ", ".join(colorize(fmt % (colors[n], v, n)) for (n, v) in stat.items())
        duration: Optional[float] = batch.total_duration if batch.total_duration > 0 else None
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

    def nvtest_invocation(self, batch: TestBatch, node_count: Optional[int] = None) -> str:
        """Write the nvtest invocation used to run this batch."""
        fp = io.StringIO()
        fp.write("nvtest ")
        if config.get("config:debug"):
            fp.write("-d ")
        fp.write(f"-C {batch.root} run -rv ")
        if config.get("option:fail_fast"):
            fp.write("--fail-fast ")
        if config.get("option:plugin_dirs"):
            for p in config.get("option:plugin_dirs"):
                fp.write(f"-p {p} ")
        if workers := self.rh["batch:workers"]:
            fp.write(f"-l session:workers={workers} ")
        if node_count is None:
            node_count = math.ceil(batch.max_cpus_required / self.scheduler.config.cpus_per_node)
        fp.write(f"-l session:cpu_count={node_count * self.scheduler.config.cpus_per_node} ")
        fp.write(f"-l test:timeoutx={self.timeoutx} ")
        fp.write(f"^{batch.lot_no}:{batch.batch_no}")
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


def factory(rh: ResourceHandler) -> "AbstractTestRunner":
    runner: "AbstractTestRunner"
    if rh["batch:scheduler"] is None:
        runner = TestCaseRunner(rh)
    else:
        runner = BatchRunner(rh)
    return runner
