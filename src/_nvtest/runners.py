import io
import os
import signal
import subprocess
import time
from typing import IO
from typing import Any
from typing import Optional

from . import config
from .abc import AbstractTestCase
from .abc import AbstractTestRunner
from .error import diff_exit_status
from .resource import ResourceHandler
from .status import Status
from .test.batch import TestBatch
from .test.case import TestCase
from .third_party.color import colorize
from .util import logging
from .util.filesystem import which
from .util.filesystem import working_dir
from .util.time import hhmmss
from .util.time import timestamp


class TestCaseRunner(AbstractTestRunner):
    def __init__(self, rh: ResourceHandler) -> None:
        self.timeoutx = rh["test:timeoutx"]
        super().__init__(rh)

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        return name in ("direct", None)

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
    run as exclusive test cases

    """

    shell = "/bin/sh"
    command_name = "batch-runner"

    def __init__(self, rh: ResourceHandler) -> None:
        super().__init__(rh)
        self.extra_args = rh["batch:runner_args"] or []
        # this is the number of workers for the launched batch
        self.workers: Optional[int] = rh["batch:workers"]
        self.timeoutx: float = rh["test:timeoutx"] or 1.0
        self.default_args = self.read_default_args_from_config()
        command = which(self.command_name)
        if command is None:
            raise ValueError(f"{self.command_name} not found on PATH")
        self.exe: str = command

    def read_default_args_from_config(self) -> list[str]:
        default_args = config.get("batch:runner_args")
        return list(default_args or [])

    def write_submission_script(self, batch: TestBatch, file: IO[Any]) -> None:
        raise NotImplementedError

    def run(self, batch: AbstractTestCase, stage: str = "test") -> None:
        assert isinstance(batch, TestBatch)
        try:
            logging.debug(f"Running batch {batch.batch_no}")
            start = time.monotonic()
            self.run_batch(batch)
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

    def run_batch(self, batch: TestBatch) -> None:
        raise NotImplementedError

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

    def qtime(self, batch: TestBatch, minutes: bool = False) -> float:
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
        if not minutes:
            return total_runtime
        qtime_in_minutes = total_runtime // 60
        if total_runtime % 60 > 0:
            qtime_in_minutes += 1
        return qtime_in_minutes

    def nvtest_invocation(
        self, *, batch: TestBatch, workers: Optional[int] = None, cpus: Optional[int] = None
    ) -> str:
        fp = io.StringIO()
        fp.write("nvtest ")
        if config.get("config:debug"):
            fp.write("-d ")
        fp.write(f"-C {batch.root} run -rv ")
        if config.get("option:fail_fast"):
            fp.write("--fail-fast ")
        if workers is not None:
            fp.write(f"-l session:workers={workers} ")
        if cpus is None:
            cpu_ids = ",".join(str(_) for _ in batch.cpu_ids)
            fp.write(f"-l session:cpu_ids={cpu_ids} ")
        else:
            fp.write(f"-l session:cpu_count={cpus} ")
        fp.write(f"-l test:timeoutx={self.timeoutx} ")
        fp.write(f"^{batch.lot_no}:{batch.batch_no}")
        return fp.getvalue()
