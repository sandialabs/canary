# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any
from typing import Generator

from ... import config
from ...test.batch import TestBatch
from ..hookspec import hookimpl


@hookimpl(tryfirst=True, wrapper=True)
def canary_testbatch_setup(batch: TestBatch) -> Generator[Any, Any, Any]:
    if not config.getoption("dont_restage"):
        batch.setup()
    res = yield
    batch.save()
    return res


@hookimpl(tryfirst=True, wrapper=True)
def canary_testbatch_run(batch: TestBatch, qsize: int, qrank: int) -> Generator[Any, Any, Any]:
    batch.run(qsize=qsize, qrank=qrank)
    res = yield
    return res


@hookimpl(tryfirst=True, wrapper=True)
def canary_testbatch_finish(batch: TestBatch) -> Generator[Any, Any, Any]:
    batch.finish()
    res = yield
    return res
