# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import glob
import json
import math
import os
from typing import Any
from typing import Sequence

from .. import config
from ..status import Status
from ..util import logging
from ..util.filesystem import mkdirp
from ..util.hash import hashit
from .atc import AbstractTestCase
from .case import TestCase


class TestBatch(AbstractTestCase):
    """A batch of test cases

    Args:
      cases: The list of test cases in this batch

    """

    def __init__(
        self,
        cases: Sequence[TestCase],
        runtime: float | None = None,
    ) -> None:
        super().__init__()
        self.validate(cases)
        self.cases = list(cases)
        self._id = hashit(",".join(case.id for case in self.cases), length=20)
        self.total_duration: float = -1
        self._submit_cpus = 1
        self._submit_gpus = 0
        self.max_cpus_required = max([case.cpus for case in self.cases])
        self.max_gpus_required = max([case.gpus for case in self.cases])
        self._runtime: float | None = runtime
        self._status: Status
        for case in self.cases:
            if any(dep not in self.cases for dep in case.dependencies):
                self._status = Status("pending")
                break
        else:
            self._status = Status("ready")

    def __iter__(self):
        return iter(self.cases)

    def __len__(self) -> int:
        return len(self.cases)

    def __repr__(self) -> str:
        case_repr: str
        if len(self.cases) <= 3:
            case_repr = ",".join(repr(case) for case in self.cases)
        else:
            case_repr = f"{self.cases[0]!r},{self.cases[1]!r},...,{self.cases[-1]!r}"
        return f"TestBatch({case_repr})"

    @property
    def variables(self) -> dict[str, str | None]:
        return {"CANARY_BATCH_ID": str(self.id)}

    @property
    def runtime(self) -> float:
        from ..util import partitioning

        if self._runtime is None:
            if len(self.cases) == 1:
                self._runtime = self.cases[0].runtime
            else:
                _, height = partitioning.packed_perimeter(self.cases)
                t = sum(c.runtime for c in self)
                self._runtime = float(min(height, t))
        assert self._runtime is not None
        return self._runtime

    def size(self) -> float:
        vec = [self.runtime, self.cpus, self.gpus]
        return math.sqrt(sum(_**2 for _ in vec))

    def required_resources(self) -> list[list[dict[str, Any]]]:
        group: list[dict[str, Any]] = [{"type": "cpus", "slots": 1} for _ in range(self.cpus)]
        # by default, only one resource group is returned
        return [group]

    @property
    def duration(self):
        start = min(case.start for case in self)
        stop = max(case.stop for case in self)
        if start == -1 or stop == -1:
            return -1
        return stop - start

    def validate(self, cases: Sequence[TestCase]):
        errors = 0
        for case in cases:
            if case.masked():
                logging.fatal(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.masked():
                    errors += 1
                    logging.fatal(f"{dep}: dependent of {case} is masked")
        if errors:
            raise ValueError("Stopping due to previous errors")

    def command(self, stage: str = "run") -> list[str]:
        raise NotImplementedError

    @property
    def cputime(self) -> float:
        return sum(case.cpus * min(case.runtime, 5.0) for case in self) * 1.5

    @property
    def has_dependencies(self) -> bool:
        return any(case.dependencies for case in self.cases)

    @property
    def cpus(self) -> int:
        return self._submit_cpus

    @property
    def gpus(self) -> int:
        return self._submit_gpus

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
    def status(self, arg: Status | dict[str, str]) -> None:
        if isinstance(arg, Status):
            self._status.set(arg.value, details=arg.details)
        else:
            self._status.set(arg["value"], details=arg["details"])

    def refresh(self) -> None:
        for case in self:
            case.refresh()

    @property
    def id(self) -> str:
        return self._id

    def submission_script_filename(self) -> str:
        return os.path.join(self.stage(self.id), "canary-inp.sh")

    @staticmethod
    def logfile(batch_id: str) -> str:
        """Get the path of the batch log file"""
        return os.path.join(TestBatch.stage(batch_id), "canary-out.txt")

    @property
    def path(self) -> str:
        return os.path.join(".canary/batches", self.id[:2], self.id[2:])

    def save(self):
        f = os.path.join(self.stage(self.id), "index")
        mkdirp(os.path.dirname(f))
        with open(f, "w") as fh:
            json.dump([case.id for case in self], fh, indent=2)

    @staticmethod
    def loadindex(batch_id: str) -> list[str] | None:
        try:
            full_batch_id = TestBatch.find(batch_id)
        except BatchNotFound:
            return None
        stage = TestBatch.stage(full_batch_id)
        f = os.path.join(stage, "index")
        if not os.path.exists(f):
            return None
        with open(f, "r") as fh:
            return json.load(fh)

    @staticmethod
    def stage(batch_id: str) -> str:
        work_tree = config.session.work_tree
        assert work_tree is not None
        root = os.path.join(work_tree, ".canary/batches", batch_id[:2])
        if os.path.exists(root) and os.path.exists(os.path.join(root, batch_id[2:])):
            return os.path.join(root, batch_id[2:])
        pattern = os.path.join(root, f"{batch_id[2:]}*")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
        return os.path.join(root, batch_id[2:])

    @staticmethod
    def find(batch_id: str) -> str:
        """Find the full batch ID from batch_id"""
        work_tree = config.session.work_tree
        assert work_tree is not None
        pattern = os.path.join(work_tree, ".canary/batches", batch_id[:2], f"{batch_id[2:]}*")
        candidates = glob.glob(pattern)
        if not candidates:
            raise BatchNotFound(f"cannot find stage for batch {batch_id}")
        return "".join(candidates[0].split(os.path.sep)[-2:])


class BatchNotFound(Exception):
    pass
