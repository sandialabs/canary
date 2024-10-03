import io
import os
import time
from io import StringIO
from typing import Any
from typing import Optional
from typing import TextIO
from typing import Type
from typing import Union

from .. import config
from ..resources import calculate_allocations
from ..test.status import Status
from ..third_party.color import colorize
from ..util import logging
from ..util import partition
from ..util.filesystem import which
from ..util.time import hhmmss
from .case import TestCase
from .runner import Runner


class BatchRunner(Runner):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch
      batch_no: The index of this batch in the group
      nbatches: The number of partitions in the group
      lot_no: The lot number of the group

    """

    shell = "/bin/sh"
    command_name = "sh"

    REGISTRY: set[Type["BatchRunner"]] = set()

    def __init_subclass__(cls, **kwargs):
        cls.REGISTRY.add(cls)
        return super().__init_subclass__(**kwargs)

    def __init__(
        self,
        cases: Union[list[TestCase], set[TestCase]],
        batch_no: int,
        nbatches: int,
        lot_no: int = 1,
    ) -> None:
        super().__init__()
        self.validate(cases)
        self.cases = list(cases)
        self.id = self.batch_no = batch_no
        self.nbatches = nbatches
        self.lot_no = lot_no
        self.name = f"nv.{self.lot_no}/{self.batch_no}/{self.nbatches}"
        self._status = Status("created")
        first = next(iter(cases))
        self.root = first.exec_root
        self.total_duration: float = -1
        self.max_cpus_required = max([case.cpus for case in self.cases])
        self.max_gpus_required = max([case.gpus for case in self.cases])
        self._runtime: float
        if len(self.cases) == 1:
            self._runtime = self.cases[0].runtime
        else:
            ns = calculate_allocations(self.max_cpus_required)
            grid = partition.tile(self.cases, ns.cores_per_node * ns.nodes)
            self._runtime = sum([max(case.runtime for case in row) for row in grid])
        self.default_args: list[str] = []
        command = which(self.command_name)
        if command is None:
            raise ValueError(f"{self.command_name} not found on PATH")
        self.command: str = command

    def __iter__(self):
        return iter(self.cases)

    def __len__(self):
        return len(self.cases)

    @staticmethod
    def matches(name: Optional[str]) -> bool:
        raise NotImplementedError

    @property
    def variables(self) -> dict[str, Optional[str]]:
        return {
            "NVTEST_LOT_NO": str(self.lot_no),
            "NVTEST_BATCH_NO": str(self.batch_no),
            "NVTEST_NBATCHES": str(self.nbatches),
            "NVTEST_LEVEL": "1",
            "NVTEST_DISABLE_KB": "1",
            "NVTEST_BATCH_SCHEDULER": None,
            "NVTEST_BATCH_SCHEDULER_ARGS": None,
            "NVTEST_BATCH_LENGTH": None,
        }

    def dump_variables(self, stream: TextIO) -> None:
        for var, val in self.variables.items():
            if val is None:
                stream.write(f"unset {var}\n")
            else:
                stream.write(f"export {var}={val}\n")

    def nvtest_invocation(
        self, *, workers: int, cpus: Optional[int] = None, timeoutx: float = 1.0
    ) -> str:
        fp = StringIO()
        fp.write("nvtest ")
        if config.get("config:debug"):
            fp.write("-d ")
        fp.write(f"-C {self.root} run -rv ")
        if config.get("option:fail_fast"):
            fp.write("--fail-fast ")
        fp.write(f"-l session:workers={workers} ")
        if cpus is None:
            cpu_ids = ",".join(str(_) for _ in self.cpu_ids)
            fp.write(f"-l session:cpu_ids={cpu_ids} ")
        else:
            fp.write(f"-l session:cpu_count={cpus} ")
        fp.write(f"-l test:timeoutx={timeoutx} ")
        fp.write(f"^{self.lot_no}:{self.batch_no}")
        return fp.getvalue()

    def validate(self, cases: Union[list[TestCase], set[TestCase]]):
        errors = 0
        for case in cases:
            if case.mask:
                logging.fatal(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.mask:
                    errors += 1
                    logging.fatal(f"{dep}: dependent of {case} is masked")
        if errors:
            raise ValueError("Stopping due to previous errors")

    @property
    def cputime(self) -> float:
        return sum(case.cpus * min(case.runtime, 5.0) for case in self) * 1.5

    @property
    def runtime(self) -> float:
        return self._runtime

    @property
    def has_dependencies(self) -> bool:
        return any(case.dependencies for case in self.cases)

    @property
    def cpus(self) -> int:
        return self.max_cpus_required

    @property
    def gpus(self) -> int:
        return self.max_gpus_required

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
    def status(self, arg: Union[Status, list[str]]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg[0], details=arg[1])

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    @property
    def stage(self):
        return os.path.join(self.root, ".nvtest/batches", str(self.lot_no))

    def submission_script_filename(self) -> str:
        basename = f"batch.{self.batch_no}-inp.sh"
        return os.path.join(self.stage, basename)

    def logfile(self) -> str:
        basename = f"batch.{self.batch_no}-out.txt"
        return os.path.join(self.stage, basename)

    def setup(self) -> None:
        for case in self.cases:
            if any(dep not in self.cases for dep in case.dependencies):
                self._status.set("pending")
                break
        else:
            self._status.set("ready")
        self.read_default_args_from_config()

    def read_default_args_from_config(self) -> None:
        default_args = config.get("batch:scheduler_args")
        if default_args is not None:
            self.default_args.extend(default_args)

    def _run(self, *args: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def start_msg(self) -> str:
        n = len(self.cases)
        return f"SUBMITTING: Batch {self.batch_no} of {self.nbatches} ({n} tests)"

    def end_msg(self) -> str:
        stat: dict[str, int] = {}
        for case in self.cases:
            stat[case.status.value] = stat.get(case.status.value, 0) + 1
        fmt = "@%s{%d %s}"
        colors = Status.colors
        st_stat = ", ".join(colorize(fmt % (colors[n], v, n)) for (n, v) in stat.items())
        duration: Optional[float] = self.total_duration if self.total_duration > 0 else None
        s = io.StringIO()
        s.write(f"FINISHED: Batch {self.batch_no} of {self.nbatches}, {st_stat} ")
        s.write(f"(time: {hhmmss(duration, threshold=0)}")
        if any(_.start > 0 for _ in self) and any(_.finish > 0 for _ in self):
            ti = min(_.start for _ in self if _.start > 0)
            tf = max(_.finish for _ in self if _.finish > 0)
            s.write(f", running: {hhmmss(tf - ti, threshold=0)}")
            if duration:
                qtime = max(duration - (tf - ti), 0)
                s.write(f", queued: {hhmmss(qtime, threshold=0)}")
        s.write(")")
        return s.getvalue()

    def run(self, *args: str, **kwargs: Any) -> None:
        try:
            start = time.monotonic()
            self._run(*args, **kwargs)
        finally:
            self.total_duration = time.monotonic() - start
            self.refresh()
            for case in self:
                if case.status == "ready":
                    case.status.set("failed", "case failed to start")
                    case.save()
                elif case.status == "running":
                    case.status.set("cancelled", "batch cancelled")
                    case.save()
        return

    def qtime(self, minutes: bool = False) -> float:
        if len(self.cases) == 1:
            return self.cases[0].timeout
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
            total_runtime *= 1.1
        if not minutes:
            return total_runtime
        qtime_in_minutes = total_runtime // 60
        if total_runtime % 60 > 0:
            qtime_in_minutes += 1
        return qtime_in_minutes


def factory(
    cases: Union[list[TestCase], set[TestCase]],
    batch_no: int,
    nbatches: int,
    lot_no: int = 1,
    type: Optional[str] = None,
) -> BatchRunner:
    batch_runner: BatchRunner

    for T in BatchRunner.REGISTRY:
        if T.matches(type):
            batch_runner = T(cases, batch_no, nbatches, lot_no)
            break
    else:
        raise ValueError(f"{type}: Unknown batch scheduler")
    batch_runner.setup()
    return batch_runner
