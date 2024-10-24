import abc
import io
import os
import signal
import subprocess
import time
from typing import Any
from typing import Optional

from . import config
from . import plugin
from .atc import AbstractTestCase
from .error import diff_exit_status
from .hpc_scheduler import HPCScheduler
from .resource import ResourceHandler
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

    def __init__(self, rh: ResourceHandler) -> None:
        self.rh = rh

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
        self.timeoutx = self.rh["test:timeoutx"]

    def run(self, case: "AbstractTestCase", stage: str = "test") -> None:
        assert isinstance(case, TestCase)
        assert stage in ("test", "analyze")
        try:
            case.start = timestamp()
            case.status.set("running")
            case.prepare_for_launch(stage=stage)
            timeout = case.timeout * self.timeoutx
            with working_dir(case.exec_dir):
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
        super().__init__(rh)
        scheduler_name = self.rh["batch:scheduler"]
        self.scheduler: HPCScheduler
        for scheduler_type in plugin.schedulers():
            if scheduler_type.matches(scheduler_name):
                self.scheduler = scheduler_type(self.rh)
                break
        else:
            raise ValueError(f"No matching scheduler for {scheduler_name}")

    def run(self, batch: AbstractTestCase, stage: str = "test") -> None:
        assert isinstance(batch, TestBatch)
        try:
            logging.debug(f"Running batch {batch.batch_no}")
            start = time.monotonic()
            self.scheduler.submit_and_wait(batch)
        finally:
            batch.total_duration = time.monotonic() - start
            batch.refresh()
            for case in batch.cases:
                if case.status == "ready":
                    case.status.set("failed", "case failed to start")
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


def factory(rh: ResourceHandler) -> "AbstractTestRunner":
    runner: "AbstractTestRunner"
    if rh["batch:scheduler"] is None:
        runner = TestCaseRunner(rh)
    else:
        runner = BatchRunner(rh)
    return runner
