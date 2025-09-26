# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os

import canary

from .backend import BatchBackend
from .testbatch import TestBatch

logger = canary.get_logger(__name__)


class BatchExecutor(BatchBackend):
    def __init__(self, *, backend: str, batch: str, case: str | None = None) -> None:
        super().__init__(backend=backend)
        if "CANARY_BATCH_ID" not in os.environ:
            os.environ["CANARY_BATCH_ID"] = batch
        elif batch != os.environ["CANARY_BATCH_ID"]:
            raise ValueError("env batch id inconsistent with cli batch id")
        self.batch = batch
        self.cases: list[str] = []
        if case is not None:
            self.cases.append(case)
        else:
            cases = TestBatch.loadindex(self.batch)
            self.cases.extend(cases)

    @property
    def case_specs(self) -> list[str]:
        return [f"/{case}" for case in self.cases]

    @canary.hookimpl
    def canary_runtests_startup(self, args: argparse.Namespace) -> None:
        # Inject the case specs from this batch
        args.mode = "a"
        case_specs = self.case_specs
        n = len(case_specs)
        logger.info(f"Selected {n} {canary.string.pluralize('test', n)} from batch {self.batch}")
        setattr(args, "case_specs", case_specs)
