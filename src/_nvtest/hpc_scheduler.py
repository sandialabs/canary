import io
from abc import ABC
from abc import abstractmethod
from typing import IO
from typing import Any
from typing import Optional
from typing import Type

from _nvtest import config
from _nvtest.resource import ResourceHandler
from _nvtest.test.batch import TestBatch

from .util.filesystem import which


class HPCScheduler(ABC):
    """Setup and submit jobs to an HPC scheduler"""

    shell = "/bin/sh"
    command_name = "<submit-command>"
    REGISTRY: set[Type["HPCScheduler"]] = set()

    def __init_subclass__(cls) -> None:
        HPCScheduler.REGISTRY.add(cls)
        return super().__init_subclass__()

    def __init__(self, rh: ResourceHandler) -> None:
        command = which(self.command_name)
        if command is None:
            raise ValueError(f"{self.command_name} not found on PATH")
        self.rh = rh
        self.exe: str = command
        self.extra_args = self.rh["batch:scheduler_args"] or []
        # this is the number of workers for the launched batch
        self.workers: Optional[int] = self.rh["batch:workers"]
        self.timeoutx: float = self.rh["test:timeoutx"] or 1.0
        self.default_args = self.read_default_args_from_config()

    @staticmethod
    @abstractmethod
    def matches(name: Optional[str]) -> bool: ...

    @abstractmethod
    def submit_and_wait(self, batch: TestBatch) -> None: ...

    def write_submission_script(self, batch: TestBatch, file: IO[Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def poll(self, jobid: str) -> Optional[str]: ...

    @abstractmethod
    def cancel(self, jobid: str) -> None: ...

    def read_default_args_from_config(self) -> list[str]:
        default_args = config.get("batch:scheduler_args")
        return list(default_args or [])

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
