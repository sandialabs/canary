# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
from typing import Any
from typing import Sequence

import canary
from _canary.util.hash import hashit

logger = canary.get_logger(__name__)


@dataclasses.dataclass
class BatchSpec:
    cases: list[canary.TestCase]
    id: str = dataclasses.field(init=False)
    session: str = dataclasses.field(init=False)
    rparameters: dict[str, int] = dataclasses.field(init=False)
    exclusive: bool = dataclasses.field(init=False, default=False)

    def __post_init__(self) -> None:
        self.validate(self.cases)
        self.id = hashit(",".join(case.id for case in self.cases), length=20)
        self.session = self.cases[0].workspace.session
        # 1 CPU and not GPUs needed to submit this batch and wait for scheduler
        self.rparameters = {"cpus": 1, "gpus": 0}

    def validate(self, cases: Sequence[canary.TestCase]):
        errors = 0
        for case in cases:
            if case.mask:
                logger.critical(f"{case}: case is masked")
                errors += 1
            for dep in case.dependencies:
                if dep.mask:
                    errors += 1
                    logger.critical(f"{dep}: dependent of {case} is masked")
        if errors:
            raise ValueError("Stopping due to previous errors")

    def required_resources(self) -> list[dict[str, Any]]:
        return [{"type": "cpus", "slots": 1}]
