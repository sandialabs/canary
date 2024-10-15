import os
from typing import Optional
from typing import Union

from ..abc import AbstractTestCase
from ..resource import calculate_allocations
from ..status import Status
from ..util import logging
from ..util import partition
from .case import TestCase


class TestBatch(AbstractTestCase):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch
      batch_no: The index of this batch in the group
      nbatches: The number of partitions in the group
      lot_no: The lot number of the group

    """

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
        first = next(iter(cases))
        self.root = self.exec_dir = first.exec_root
        self.total_duration: float = -1
        self.max_cpus_required = self._cpus = max([case.cpus for case in self.cases])
        self.max_gpus_required = self._gpus = max([case.gpus for case in self.cases])
        self._runtime: float
        if len(self.cases) == 1:
            self._runtime = self.cases[0].runtime
        else:
            ns = calculate_allocations(self.max_cpus_required)
            grid = partition.tile(self.cases, ns.cores_per_node * ns.nodes)
            self._runtime = sum([max(case.runtime for case in row) for row in grid])
        self._status: Status
        for case in self.cases:
            if any(dep not in self.cases for dep in case.dependencies):
                self._status = Status("pending")
                break
        else:
            self._status = Status("ready")

    def __iter__(self):
        return iter(self.cases)

    def __len__(self):
        return len(self.cases)

    @property
    def variables(self) -> dict[str, Optional[str]]:
        return {
            "NVTEST_LOT_NO": str(self.lot_no),
            "NVTEST_BATCH_NO": str(self.batch_no),
            "NVTEST_NBATCHES": str(self.nbatches),
            "NVTEST_LEVEL": "1",
            "NVTEST_DISABLE_KB": "1",
            "NVTEST_BATCH_RUNNER": None,
            "NVTEST_BATCH_RUNNER_ARGS": None,
            "NVTEST_BATCH_LENGTH": None,
        }

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
        return self._cpus

    @cpus.setter
    def cpus(self, arg: int) -> None:
        self._cpus = arg

    @property
    def gpus(self) -> int:
        return self._gpus

    @gpus.setter
    def gpus(self, arg: int) -> None:
        self._gpus = arg

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
    def status(self, arg: Union[Status, dict[str, str]]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg["value"], details=arg["details"])

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
